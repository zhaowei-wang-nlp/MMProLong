"""Batching and prefix reuse must retain every page and the review contract."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
from public_vqa_pipeline import Runner, retry_after_seconds, write_json


class ThroughputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_generation_and_verification_share_full_image_prefix(self):
        r = Runner.__new__(Runner)
        r.root = self.root
        r.docs = {"doc": {"page_count": 2, "sha256": "test-sha"}}
        r._prefix_cache = {}
        r._prefix_lock = threading.Lock()
        r.disk_policy = None
        r.key = "unit-test-key"
        r.model = "test-model"
        folder = self.root / "teacher" / "doc"
        folder.mkdir(parents=True)
        for n in range(2):
            (folder / f"page{n:03d}.jpg").write_bytes(b"test-page")
        calls = []

        def complete(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                model="test-model",
                choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"items":[]}'))],
                usage=None,
            )

        r.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
        r.request("generation", "doc", "GENERATE", {"slots": [1] * 12})
        r.request("job_verify", "doc", "VERIFY", {"candidates": [1] * 12})
        first, second = [c["messages"][0]["content"] for c in calls]
        self.assertEqual(first[:-1], second[:-1])
        self.assertEqual(sum(p["type"] == "image_url" for p in first), 2)
        self.assertIn("GENERATE", first[-1]["text"])
        self.assertIn("VERIFY", second[-1]["text"])
        self.assertEqual(len(r._prefix_cache), 1)
        saved = json.loads((self.root / "calls/job_verify.json").read_text())
        self.assertEqual(saved["context_pages"], [0, 1])
        self.assertEqual(saved["requested_items"], 12)
        self.assertNotIn("unit-test-key", (self.root / "calls/job_verify.json").read_text())

    def test_document_sized_jobs_keep_all_slots(self):
        r = Runner.__new__(Runner)
        r.root = self.root
        r.docs = {"a": {}, "b": {}}
        r.plan = [{"id": f"{doc}_{i}", "document_id": doc} for doc in r.docs for i in range(12)]
        r.qa_per_call = 12
        jobs = []
        r.run_job = lambda doc, slots, round_index, job_index: jobs.append((doc, slots))
        r.run(workers=2, rounds=1)
        self.assertEqual(sorted(len(slots) for _, slots in jobs), [12, 12])
        self.assertEqual({s["id"] for _, slots in jobs for s in slots}, {s["id"] for s in r.plan})

    def test_pool_can_schedule_two_groups_per_document_at_128_concurrency(self):
        r = Runner.__new__(Runner)
        r.root = self.root
        r.docs = {str(i): {} for i in range(64)}
        r.plan = [{"id": f"slot_{doc}_{i}", "document_id": doc} for doc in r.docs for i in range(2)]
        r.qa_per_call = 1
        barrier = threading.Barrier(128, timeout=10)
        completed = []

        def job(doc, slots, round_index, job_index):
            barrier.wait()
            completed.extend(s["id"] for s in slots)

        r.run_job = job
        r.run(workers=128, rounds=1)
        self.assertEqual(len(completed), 128)
        self.assertEqual(set(completed), {s["id"] for s in r.plan})

    def novelty_runner(self, result):
        r = Runner.__new__(Runner)
        r.root, r.model = self.root, "test-model"
        r.accept_lock = threading.Lock()
        r.question_keys = {"questiona", "questionb"}
        r.request = lambda *args, **kwargs: result
        for ident in ["doc_a", "doc_b"]:
            write_json(
                self.root / "accepted" / (ident + ".json"),
                {
                    "id": ident,
                    "question": "question" + ident[-1],
                    "answer": "same answer",
                    "document_id": "doc",
                    "evidence_pages": [0],
                    "evidence_facts": [],
                },
            )
        return r

    def test_novelty_rejects_only_provisional_duplicate_and_clears_question_key(self):
        r = self.novelty_runner(
            {
                "reviewed_ids": ["doc_a", "doc_b"],
                "duplicates": [{"id": "doc_b", "duplicate_of": "doc_a", "reason": "paraphrase of the same target"}],
            }
        )
        r.audit_document_novelty("doc")
        self.assertTrue((self.root / "accepted/doc_a.json").exists())
        self.assertFalse((self.root / "accepted/doc_b.json").exists())
        self.assertNotIn("questionb", r.question_keys)
        self.assertEqual(len(list((self.root / "rejected").glob("*.json"))), 1)
        kept = json.loads((self.root / "accepted/doc_a.json").read_text())
        self.assertTrue(kept["document_novelty_review"]["distinct"])

    def test_incomplete_or_invalid_novelty_response_cannot_pass_silently(self):
        for result in [
            {"reviewed_ids": ["doc_a"], "duplicates": []},
            {
                "reviewed_ids": ["doc_a", "doc_b"],
                "duplicates": [{"id": "unknown", "duplicate_of": "doc_a", "reason": "bad id"}],
            },
            {
                "reviewed_ids": ["doc_a", "doc_b"],
                "duplicates": [{"id": "doc_a", "duplicate_of": "doc_b", "reason": "reverse"}],
            },
        ]:
            with self.subTest(result=result):
                r = self.novelty_runner(result)
                with self.assertRaises(ValueError):
                    r.audit_document_novelty("doc")
                self.assertEqual(len(list((self.root / "accepted").glob("*.json"))), 2)

    def test_pair_audit_uses_qa_text_and_no_pdf_pages(self):
        r = self.novelty_runner({})
        calls = []

        def request(*args, **kwargs):
            calls.append((args, kwargs))
            return {"reviewed_ids": ["doc_a", "doc_b"], "duplicates": []}

        r.request = request
        r.audit_document_novelty("doc")
        self.assertTrue(calls[0][1]["text_only"])
        self.assertEqual(len(calls[0][0][3]["candidates"]), 2)
        for p in (self.root / "accepted").glob("*.json"):
            self.assertTrue(json.loads(p.read_text())["document_novelty_review"]["distinct"])

    def test_provider_retry_delays_are_respected(self):
        error = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "17"}))
        self.assertEqual(retry_after_seconds(error, 0), 17)
        error.response.headers = {"retry-after-ms": "2500"}
        self.assertEqual(retry_after_seconds(error, 0), 2.5)
        error.response.headers = {}
        self.assertEqual(retry_after_seconds(error, 1), 40)


if __name__ == "__main__":
    unittest.main()
