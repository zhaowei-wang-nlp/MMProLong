"""Publication inputs retain full context and recover safely across worker restarts."""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
from journal_intake import claim_ready, crossref_candidate, domain_order, prepare_candidate, safe_link
from public_vqa_pipeline import Runner, prepare, write_json


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = {
            "min_free_gib": 0,
            "write_headroom_mib": 0,
            "min_document_pages": 14,
            "max_document_pages": 50,
            "min_content_pages": 9,
            "min_content_fraction": 0.6,
            "min_sample_tokens": 32768,
            "max_sample_tokens": 126976,
            "shared_images": True,
            "source_domains": ["Physics", "Biology", "Economics"],
        }

    def candidate(self, license_url="http://creativecommons.org/licenses/by/4.0/"):
        return crossref_candidate(
            {"DOI": "10.1371/journal.pone.0283092", "title": ["Test"], "license": [{"URL": license_url}]}, "Economics"
        )

    def test_license_variants_and_untrusted_license_host_are_not_accepted(self):
        self.assertIsNotNone(self.candidate())
        for url in [
            "https://creativecommons.org/licenses/by-nc/4.0/",
            "https://creativecommons.org/licenses/by/3.0/",
            "https://example.org/licenses/by/4.0/",
            "https://creativecommons.org.evil.test/licenses/by/4.0/",
        ]:
            self.assertIsNone(self.candidate(url))

    def test_dominant_domain_is_held_even_if_it_has_many_available_candidates(self):
        order = domain_order({"Physics": 1300, "Biology": 29, "Economics": 83}, self.policy)
        self.assertEqual(order, ["Biology", "Economics"])

    def test_complete_pdf_is_prepared_and_partial_transfer_can_resume(self):
        import fitz

        candidate = self.candidate()
        ident = candidate["id"]
        intake = self.root / "intake"
        item = intake / "items" / ident
        pdf_path = item / "sources" / (ident + ".pdf")
        pdf_path.parent.mkdir(parents=True)
        with fitz.open() as pdf:
            for i in range(14):
                page = pdf.new_page()
                page.insert_text((40, 60), f"Complete context page {i}: scientific methods and empirical results.")
            pdf.save(pdf_path)
        result = prepare_candidate(candidate, str(intake), self.policy)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["document"]["page_count"], 14)
        self.assertEqual(len(list((item / "images" / ident).glob("*.png"))), 14)
        with patch("fitz.open", side_effect=AssertionError("Prefetched PDF must not be parsed a second time")):
            cached = prepare(
                item, manifest_only=True, policy=self.policy, prepared_documents={ident: result["document"]}
            )
        self.assertEqual(cached, [result["document"]])
        original_pdf = pdf_path.read_bytes()
        pdf_path.write_bytes(original_pdf + b"changed")
        with self.assertRaises(ValueError):
            prepare(item, manifest_only=True, policy=self.policy, prepared_documents={ident: result["document"]})
        pdf_path.write_bytes(original_pdf)
        batch = self.root / "batches" / "batch_00000"
        # Simulate interruption after linking the PDF but before transferring images.
        safe_link(pdf_path, self.root / "sources" / pdf_path.name)
        write_json(item / "claim.json", {"batch": batch.name, "document_id": ident})
        from collections import Counter

        docs = claim_ready(self.root, batch, 1, Counter({"Physics": 1300}), self.policy)
        self.assertEqual([d["id"] for d in docs], [ident])
        self.assertEqual(len(list((self.root / "images" / ident).glob("*.png"))), 14)
        self.assertTrue((self.root / "sources" / (ident + ".license-record.json")).exists())
        self.assertTrue((intake / "receipts" / (ident + ".json")).exists())
        self.assertFalse(item.exists())

    def test_conflicting_existing_asset_is_never_overwritten(self):
        a, b = self.root / "a", self.root / "b"
        a.write_bytes(b"one")
        b.write_bytes(b"two")
        with self.assertRaises(ValueError):
            safe_link(a, b)
        self.assertEqual(b.read_bytes(), b"two")

    def test_document_retry_does_not_wait_for_another_documents_slow_request(self):
        r = Runner.__new__(Runner)
        r.root = self.root
        r.docs = {"slow": {}, "fast": {}}
        r.plan = [{"id": doc, "document_id": doc} for doc in r.docs]
        r.qa_per_call = 1
        r.pipelined_document_jobs = True
        r.document_novelty_check = True
        fast_finished = threading.Event()
        calls = []

        def job(doc, slots, round_index, job_index):
            calls.append((doc, round_index))
            if doc == "slow":
                self.assertTrue(fast_finished.wait(3), "Fast document was blocked by the slow document")
            elif round_index == 0:
                return  # First fast-document candidate fails quality; retry it immediately.
            write_json(self.root / "accepted" / (doc + ".json"), {"id": doc})

        def audit(doc):
            if doc == "fast" and (self.root / "accepted/fast.json").exists():
                fast_finished.set()

        r.run_job, r.audit_document_novelty = job, audit
        r.run(workers=2, rounds=3)
        self.assertIn(("fast", 1), calls)
        self.assertTrue(fast_finished.is_set())

    def test_unresolved_novelty_audit_still_blocks_admission(self):
        r = Runner.__new__(Runner)
        r.root, r.docs = self.root, {"doc": {}}
        r.plan = [{"id": "doc", "document_id": "doc"}]
        r.qa_per_call = 1
        r.pipelined_document_jobs = r.document_novelty_check = True
        r.run_job = lambda *args: write_json(self.root / "accepted/doc.json", {"id": "doc"})
        r.audit_document_novelty = lambda _: (_ for _ in ()).throw(ValueError("incomplete audit"))
        with self.assertRaises(ValueError):
            r.run(workers=1, rounds=2)
        self.assertTrue((self.root / "accepted/doc.json").exists())


if __name__ == "__main__":
    unittest.main()
