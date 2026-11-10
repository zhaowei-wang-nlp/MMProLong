import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from data_synthesis_doc_vqa.corpus_budget import DiskReserveReached, TokenLedger, check_disk


class CorpusBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = {
            "target_tokens": 250000,
            "stop_tolerance_tokens": 40000,
            "min_sample_tokens": 32768,
            "max_sample_tokens": 126976,
            "token_fractions": {
                "single": 0.36,
                "multi_local": 0.18,
                "multi_distributed": 0.18,
                "reasoning": 0.18,
                "unanswerable": 0.1,
            },
            "token_metric": "test counter",
            "min_free_gib": 10,
            "write_headroom_mib": 256,
        }
        self.ledger = TokenLedger(Path(self.temp.name), self.policy)
        self.addCleanup(self.ledger.close)
        self.doc = {"id": "document", "page_count": 40, "sha256": "test-sha", "license": "CC-BY-4.0"}

    def row(self, ident):
        return {
            "id": ident,
            "document_id": "document",
            "question": "Question " + ident,
            "answer": "answer",
            "answerable": True,
            "evidence_pages": [2],
            "evidence_facts": [{"page": 2, "fact": "fact"}],
            "slot": {"kind": "single", "needle_count": 1, "allowed_evidence_pages": [2]},
            "context_sha256": "test-sha",
            "verification_context_pages": list(range(40)),
            "verification": {
                "checked_all_pages": True,
                "context_page_count": 40,
                "question_clear": True,
                "task_label_correct": True,
                "no_unsupported_claims": True,
                "can_answer_from_context": True,
                "answer_correct": True,
                "evidence_correct": True,
            },
        }

    def test_budget_uses_valid_tokens_and_never_exceeds_target(self):
        self.assertEqual(self.ledger.admit(self.row("a"), self.doc, 100000), "admitted")
        self.assertEqual(self.ledger.admit(self.row("b"), self.doc, 100000), "admitted")
        self.assertEqual(self.ledger.admit(self.row("c"), self.doc, 60000), "would_exceed_budget")
        self.assertEqual(self.ledger.admit(self.row("d"), self.doc, 40000), "admitted")
        self.assertEqual(self.ledger.status()["accepted_tokens"], 240000)
        self.assertTrue(self.ledger.status()["target_reached"])
        self.assertEqual(self.ledger.admit(self.row("e"), self.doc, 32768), "target_reached")

    def test_duplicates_different_ids_do_not_inflate_budget(self):
        self.ledger.admit(self.row("a"), self.doc, 100000)
        duplicate = {**self.row("a"), "id": "new-id", "answer": "different wording"}
        self.assertEqual(self.ledger.admit(duplicate, self.doc, 100000), "duplicate")
        self.assertEqual(self.ledger.status()["accepted_tokens"], 100000)

    def test_rights_hold_and_failed_review_are_excluded(self):
        self.assertEqual(
            self.ledger.admit(self.row("a"), {**self.doc, "exclude_from_public_release": True}, 100000), "rights_hold"
        )
        r = self.row("b")
        r["verification"]["answer_correct"] = False
        self.assertEqual(self.ledger.admit(r, self.doc, 100000), "quality_rejected")
        self.assertEqual(self.ledger.status()["accepted_tokens"], 0)

    def test_required_novelty_review_is_bound_to_the_admitted_question(self):
        r = self.row("a")
        r["slot"]["require_document_novelty"] = True
        self.assertEqual(self.ledger.admit(r, self.doc, 100000), "novelty_review_missing")
        r["document_novelty_review"] = {"distinct": True, "compared_ids": ["a"], "question_sha256": "wrong"}
        self.assertEqual(self.ledger.admit(r, self.doc, 100000), "novelty_review_missing")
        r["document_novelty_review"]["question_sha256"] = hashlib.sha256(r["question"].encode()).hexdigest()
        self.assertEqual(self.ledger.admit(r, self.doc, 100000), "admitted")

    def test_two_questions_per_document_keep_all_five_kinds_in_corpus(self):
        import sys
        from collections import Counter

        source = Path(__file__).parents[2] / "data_synthesis_doc_vqa"
        sys.path.insert(0, str(source))
        self.addCleanup(lambda: sys.path.remove(str(source)))
        from local_corpus import Corpus

        c = Corpus.__new__(Corpus)
        self.ledger.policy["target_tokens"] = 5000000000
        c.ledger, c.policy, c.state = (
            self.ledger,
            {**self.policy, "questions_per_document": 2, "document_novelty_check": True},
            {"batch_index": 46},
        )
        docs = [{"id": str(i), "content_page_count": 30, "image_tokens": [2000] * 30} for i in range(64)]
        plan = c.make_plan(docs)
        self.assertEqual(Counter(s["document_id"] for s in plan), {d["id"]: 2 for d in docs})
        self.assertEqual({s["kind"] for s in plan}, set(self.policy["token_fractions"]))
        self.assertTrue(all(s["require_document_novelty"] for s in plan))

    def test_later_source_hold_removes_its_tokens(self):
        self.ledger.admit(self.row("a"), self.doc, 100000)
        self.ledger.hold_documents(["document"])
        self.assertEqual(self.ledger.status()["accepted_tokens"], 0)

    def test_restart_preserves_progress(self):
        self.ledger.admit(self.row("a"), self.doc, 100000)
        other = TokenLedger(Path(self.temp.name), self.policy)
        self.addCleanup(other.close)
        self.assertEqual(other.status()["accepted_samples"], 1)

    def test_disk_reserve_accounts_for_upcoming_write(self):
        reserve = 10 * 1024**3 + 256 * 1024**2
        with patch(
            "data_synthesis_doc_vqa.corpus_budget.shutil.disk_usage", return_value=SimpleNamespace(free=reserve + 999)
        ):
            with self.assertRaises(DiskReserveReached):
                check_disk(self.temp.name, self.policy, 1000)
        with patch(
            "data_synthesis_doc_vqa.corpus_budget.shutil.disk_usage", return_value=SimpleNamespace(free=reserve + 1000)
        ):
            self.assertEqual(check_disk(self.temp.name, self.policy, 1000), reserve + 1000)

    def test_single_positions_cycle_by_type_not_document_slot(self):
        import sys
        from collections import Counter

        source = Path(__file__).parents[2] / "data_synthesis_doc_vqa"
        sys.path.insert(0, str(source))
        self.addCleanup(lambda: sys.path.remove(str(source)))
        from local_corpus import Corpus

        corpus = Corpus.__new__(Corpus)
        self.ledger.policy["target_tokens"] = 5000000000
        corpus.ledger = self.ledger
        corpus.policy = {**self.policy, "questions_per_document": 12}
        corpus.state = {"batch_index": 0}
        docs = [{"id": str(i), "content_page_count": 32, "image_tokens": [2500] * 40} for i in range(12)]
        plan = corpus.make_plan(docs)
        positions = Counter(s["allowed_evidence_pages"][0] // 8 for s in plan if s["kind"] == "single")
        self.assertEqual(set(positions), {0, 1, 2, 3})
        self.assertLessEqual(max(positions.values()) - min(positions.values()), 1)


if __name__ == "__main__":
    unittest.main()
