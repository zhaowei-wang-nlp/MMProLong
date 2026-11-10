"""The document agent must actually receive evidence before submitting a candidate."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
from agentic_vqa import DocumentAgent
from document_agent_tools import DocumentTools


class DocumentAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pages").mkdir()
        (self.root / "document.json").write_text(
            json.dumps({"id": "doc", "title": "Test", "page_count": 3, "sha256": "test"})
        )
        (self.root / "page_text.json").write_text(
            json.dumps([{"page": i, "text": f"Fact {i}; alpha synonym"} for i in range(3)])
        )
        for i in range(3):
            (self.root / "pages" / f"page{i:03d}.png").write_bytes(b"test-image")

    def test_search_covers_all_text_but_does_not_claim_it_was_read(self):
        tools = DocumentTools(self.root)
        result = tools.search(["alpha"])
        self.assertEqual(result["scanned_text_pages"], [0, 1, 2])
        self.assertEqual(result["match_count"], 3)
        self.assertEqual(tools.text_pages_read, set())

    def test_tools_reject_paths_and_arbitrary_execution(self):
        tools = DocumentTools(self.root)
        with self.assertRaises(ValueError):
            tools.read(["../../secret"])
        with self.assertRaises(ValueError):
            tools.call("exec", {"command": "anything"})
        with self.assertRaises(ValueError):
            tools.calculate("__import__", [1, 2])
        self.assertEqual(tools.calculate("/", [500, 25])["result"], 20)

    def test_no_absence_claim_from_search_results_alone(self):
        agent = DocumentAgent(None, "test", "test", self.root, self.root / "trace")
        row = {
            "id": "u",
            "status": "candidate",
            "question": "What was the omitted value?",
            "answer": "Not answerable.",
            "answerable": False,
            "evidence_pages": [],
            "related_context_pages": [0],
            "missing_information": "A value",
        }
        slot = {"id": "u", "kind": "unanswerable", "needle_count": 0}
        agent.visible_image_pages.add(0)
        agent.toolbox.search(["value"])
        self.assertTrue(any("complete extracted text" in x for x in agent.candidate_errors(row, slot)))
        agent.visible_text_pages.update([0, 1, 2])
        self.assertEqual(agent.candidate_errors(row, slot), [])

    def test_image_path_only_does_not_satisfy_viewing_requirement(self):
        agent = DocumentAgent(None, "test", "test", self.root, self.root / "trace")
        agent.toolbox.read([0, 2])
        row = {
            "id": "q",
            "status": "candidate",
            "question": "Combine facts?",
            "answer": "a and b",
            "answerable": True,
            "evidence_pages": [0, 2],
            "evidence_facts": [
                {"page": 0, "fact": "Fact A", "why_necessary": "A"},
                {"page": 2, "fact": "Fact B", "why_necessary": "B"},
            ],
        }
        slot = {
            "id": "q",
            "kind": "multi_distributed",
            "needle_count": 2,
            "allowed_evidence_pages": [0, 1, 2],
            "distance_bin": "far",
        }
        self.assertTrue(any("image" in e for e in agent.candidate_errors(row, slot)))

    def test_native_loop_delivers_images_before_accepting_finish(self):
        slot = {
            "id": "q",
            "kind": "multi_distributed",
            "needle_count": 2,
            "allowed_evidence_pages": [0, 1, 2],
            "distance_bin": "far",
        }
        row = {
            "id": "q",
            "status": "candidate",
            "question": "Combine facts?",
            "answer": "a and b",
            "answerable": True,
            "evidence_pages": [0, 2],
            "evidence_facts": [
                {"page": 0, "fact": "Fact A", "why_necessary": "A"},
                {"page": 2, "fact": "Fact B", "why_necessary": "B"},
            ],
        }
        requests = []

        class Call:
            def __init__(self, ident, name, args):
                self.id, self.function = ident, SimpleNamespace(name=name, arguments=json.dumps(args))

            def model_dump(self):
                return {"id": self.id, "type": "function", "function": vars(self.function)}

        def create(**kwargs):
            requests.append(json.loads(json.dumps(kwargs)))
            calls = (
                [Call("read", "read_pages", {"pages": [0, 2]}), Call("early", "finish_question", row)]
                if len(requests) == 1
                else [Call("finish", "finish_question", row)]
            )
            return SimpleNamespace(
                model="test",
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=calls))],
            )

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        agent = DocumentAgent(client, "test-key", "test-model", self.root, self.root / "trace")
        candidate, trace = agent.generate(slot, "job")
        self.assertEqual(candidate["id"], "q")
        self.assertEqual(len(requests), 2)
        first_finish = next(t for t in trace["tools"] if t["tool"] == "finish_question")
        self.assertFalse(first_finish["result"]["accepted_for_independent_verification"])
        self.assertEqual(trace["image_pages_observed"], [0, 2])
        self.assertTrue(
            any(
                isinstance(m.get("content"), list) and any(x.get("type") == "image_url" for x in m["content"])
                for m in requests[1]["messages"]
            )
        )
        self.assertNotIn("test-key", (self.root / "trace/job.json").read_text())


if __name__ == "__main__":
    unittest.main()
