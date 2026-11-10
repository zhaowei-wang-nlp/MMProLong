"""Acceptance gates for public long-document data, without model/network calls."""

import importlib.util
import unittest
from pathlib import Path


path = Path(__file__).parents[2] / "data_synthesis_doc_vqa" / "public_vqa_pipeline.py"
spec = importlib.util.spec_from_file_location("public_vqa", path)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class PublicVQATest(unittest.TestCase):
    def test_explicit_figure_notice_is_distinct_from_technical_third_party(self):
        self.assertTrue(
            pipeline.has_explicit_third_party_figure_notice(
                "Images © their respective authors, reproduced for scholarly review."
            )
        )
        self.assertFalse(
            pipeline.has_explicit_third_party_figure_notice(
                "A quantum e-commerce protocol uses an untrusted third party."
            )
        )

    def candidate(self, pages):
        return {
            "question": "Which attributes are reported?",
            "answer": "A; B",
            "answerable": True,
            "evidence_pages": pages,
            "evidence_facts": [{"page": p, "fact": "fact"} for p in pages],
        }

    def test_local_cannot_escape_its_window(self):
        slot = {"kind": "multi_local", "needle_count": 2, "allowed_evidence_pages": list(range(10, 22))}
        self.assertEqual(pipeline.validate(self.candidate([10, 21]), slot, {"page_count": 40}), [])
        self.assertTrue(pipeline.validate(self.candidate([10, 25]), slot, {"page_count": 40}))

    def test_far_means_actual_full_context_span(self):
        slot = {
            "kind": "multi_distributed",
            "needle_count": 2,
            "distance_bin": "far",
            "allowed_evidence_pages": list(range(40)),
        }
        self.assertTrue(pipeline.validate(self.candidate([15, 16]), slot, {"page_count": 40}))
        self.assertEqual(pipeline.validate(self.candidate([2, 30]), slot, {"page_count": 40}), [])
        self.assertAlmostEqual(pipeline.evidence_span([2, 30], 40), 28 / 39)

    def test_absence_is_not_a_positive_needle(self):
        row = {
            "question": "What was the omitted measurement?",
            "answer": "Not answerable.",
            "answerable": False,
            "evidence_pages": [],
            "missing_information": "measurement",
            "related_context_pages": [12],
        }
        self.assertEqual(pipeline.validate(row, {"kind": "unanswerable"}, {"page_count": 40}), [])
        row["evidence_pages"] = [12]
        self.assertTrue(pipeline.validate(row, {"kind": "unanswerable"}, {"page_count": 40}))

    def test_local_negative_review_cannot_certify_full_context(self):
        review = dict(
            checked_all_pages=True,
            context_page_count=10,
            question_clear=True,
            task_label_correct=True,
            no_unsupported_claims=True,
            can_answer_from_context=False,
            absence_confirmed=True,
            not_indirectly_derivable=True,
        )
        self.assertFalse(pipeline.review_passes(review, {"kind": "unanswerable"}, 40))
        review["context_page_count"] = 40
        self.assertTrue(pipeline.review_passes(review, {"kind": "unanswerable"}, 40))

    def test_multiple_citations_do_not_prove_multiple_needed_pages(self):
        review = dict(
            checked_all_pages=True,
            context_page_count=40,
            question_clear=True,
            task_label_correct=True,
            no_unsupported_claims=True,
            can_answer_from_context=True,
            answer_correct=True,
            evidence_correct=True,
            all_cited_pages_necessary=False,
            no_single_page_shortcut=False,
        )
        self.assertFalse(pipeline.review_passes(review, {"kind": "multi_local", "needle_count": 2}, 40))

    def test_arithmetic_is_checked(self):
        row = self.candidate([7])
        row.update(answer="40.82", calculation={"operator": "-", "operands": [88.92, 48.1]})
        slot = {"kind": "reasoning", "needle_count": 1, "allowed_evidence_pages": list(range(40))}
        self.assertEqual(pipeline.validate(row, slot, {"page_count": 40}), [])
        row["answer"] = "40.28"
        self.assertTrue(pipeline.validate(row, slot, {"page_count": 40}))

    def test_printed_total_is_not_reasoning(self):
        review = dict(
            checked_all_pages=True,
            context_page_count=40,
            question_clear=True,
            task_label_correct=True,
            no_unsupported_claims=True,
            can_answer_from_context=True,
            answer_correct=True,
            evidence_correct=True,
            result_not_directly_stated=False,
        )
        slot = {"kind": "reasoning", "needle_count": 1}
        self.assertFalse(pipeline.review_passes(review, slot, 40))
        review["result_not_directly_stated"] = True
        self.assertTrue(pipeline.review_passes(review, slot, 40))

    def test_tiny_scientific_values_are_not_compared_with_cent_precision(self):
        row = self.candidate([7])
        row.update(answer="1e-12", calculation={"operator": "*", "operands": [1e-9, 1e-6]})
        slot = {"kind": "reasoning", "needle_count": 1, "allowed_evidence_pages": list(range(40))}
        self.assertTrue(pipeline.validate(row, slot, {"page_count": 40}))
        row["answer"] = "1e-15"
        self.assertEqual(pipeline.validate(row, slot, {"page_count": 40}), [])


if __name__ == "__main__":
    unittest.main()
