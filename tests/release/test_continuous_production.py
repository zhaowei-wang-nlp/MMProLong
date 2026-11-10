import base64
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
from continuous_corpus import ContinuousProduction, SharedActivity
from lossless_transport import encode_image
import transport_metrics


class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_lossless_transport_preserves_dimensions_and_rgba_including_alpha(self):
        image = Image.new("RGBA", (120, 180), (240, 238, 235, 255))
        for x in range(40):
            image.putpixel((x, x), (x * 3, 90, 10, x * 5))
        output = io.BytesIO()
        image.save(output, format="PNG")
        mime, packed = encode_image(output.getvalue(), self.root)
        restored = Image.open(io.BytesIO(packed)).convert("RGBA")
        self.assertEqual(restored.size, image.size)
        self.assertEqual(restored.tobytes(), image.tobytes())
        self.assertLessEqual(len(packed), len(output.getvalue()))
        self.assertEqual((mime, packed), encode_image(output.getvalue(), self.root))

    def test_http_trace_does_not_capture_info_or_request_secrets(self):
        transport_metrics.begin_attempt()
        transport_metrics.trace("http11.send_request_body.started", {"authorization": "secret"})
        transport_metrics.trace("http11.send_request_body.complete", {"body": "private"})
        data = transport_metrics.end_attempt()
        self.assertIn("http11.send_request_body", data)
        self.assertNotIn("secret", json.dumps(data))
        self.assertNotIn("private", json.dumps(data))

    def test_activity_is_shared_and_balanced_between_batch_workers(self):
        activity = SharedActivity(self.root)
        barrier = threading.Barrier(8)
        def call():
            activity.record(1, "job")
            barrier.wait(timeout=5)
            activity.record(-1, "job")
        threads = [threading.Thread(target=call) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        state = json.loads((self.root / "api_activity.json").read_text())
        self.assertEqual((state["active_requests"], state["peak_requests"], state["completed_attempts"]), (0, 8, 8))

    def test_free_worker_starts_next_batch_before_slow_document_finishes(self):
        production = ContinuousProduction.__new__(ContinuousProduction)
        production.root = self.root
        production.workers = 2
        production.pause_for_disk = False
        production.last_status = time.monotonic()
        production.client = None
        production.queue = deque([("a", "slow"), ("a", "fast"), ("b", "next")])
        production.recover = Mock()
        production.add_batch = Mock(return_value=False)
        next_started = threading.Event()
        finished = []
        def job(ident, start, rounds):
            if ident == "slow":
                if not next_started.wait(5):
                    raise AssertionError("Slow-document batch barrier prevented replenishment")
            elif ident == "next":
                next_started.set()
        production.runners = {name: SimpleNamespace(run_document=job) for name in ["a", "b"]}
        production.corpus = SimpleNamespace(policy={"rounds_per_batch": 3}, status=Mock(),
                                           ledger=SimpleNamespace(status=lambda: {"target_reached": len(finished) == 3}))
        production.stopping = lambda: len(finished) == 3
        def finish(name, ident, future):
            future.result()
            finished.append(ident)
        production.finish = finish
        production.run()
        self.assertTrue(next_started.is_set())
        self.assertEqual(set(finished), {"slow", "fast", "next"})

    def test_failed_document_is_not_admitted_and_retains_candidate(self):
        batch = self.root / "batches" / "batch_00001"
        batch.mkdir(parents=True)
        retained = batch / "candidate.json"
        retained.write_text('{"candidate":"retained"}')
        corpus = SimpleNamespace(root=self.root, policy={"workers": 2}, state={"processed": []}, commit=Mock())
        production = ContinuousProduction(corpus)
        runner = SimpleNamespace(root=batch, docs={"bad": {}, "pending": {}}, _agents={}, _contexts={})
        production.runners = {batch.name: runner}
        production.done = {batch.name: {}}
        future = Future()
        future.set_exception(ValueError("audit failed"))
        production.finish(batch.name, "bad", future)
        corpus.commit.assert_not_called()
        self.assertTrue(retained.exists())
        self.assertEqual(production.done[batch.name]["bad"]["error_type"], "ValueError")
        active = json.loads((self.root / "active_documents.json").read_text())
        self.assertEqual(active["document_ids"], ["pending"])


if __name__ == "__main__":
    unittest.main()
