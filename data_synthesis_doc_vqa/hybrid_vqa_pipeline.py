"""Released window generation for local tasks; document agents for global tasks."""

import hashlib
import json
import re
import time

from agentic_vqa import (
    DocumentAgent,
    complete_with_retry,
    configure_api_parallelism,
    full_document_review,
    parse_json,
    review_qualified,
)
from corpus_budget import check_disk
from public_vqa_pipeline import Runner, evidence_span, distance_bin, validate, write_json
from released_window_vqa import prepare_context, generate_window, numeric_answer, canonical_calculation


class HybridRunner(Runner):
    def __init__(self, args):
        super().__init__(args)
        self.pipelined_document_jobs = True
        from lossless_transport import configure

        configure((self.disk_policy or {}).get("lossless_image_transport", False))
        configure_api_parallelism(
            (self.disk_policy or {}).get("api_max_concurrency", 16),
            qpm_limit=(self.disk_policy or {}).get("api_qpm_limit", 1000),
        )
        self._agents = {}
        self._contexts = {}

    def activity(self, delta, job_id):
        if delta > 0 and self.disk_policy:
            check_disk(self.root, self.disk_policy, 4 * 1024**2)
        self.record_activity(delta, job_id)

    def reject(self, slot, round_index, row, reason, review=None):
        write_json(
            self.root / "rejected" / f"{slot['id']}_r{round_index:02d}_hybrid.json",
            {"candidate": row, "rejection_reasons": reason, "review": review},
        )

    def request(self, job_id, document_id, instruction, payload, *, text_only=False):
        if not text_only:
            raise ValueError("Hybrid generation and full-PDF verification use their explicit routes")
        path = self.root / "calls" / (job_id + ".json")
        expected_ids = sorted(x["id"] for x in payload["candidates"])
        if path.exists():
            saved = json.loads(path.read_text())
            try:
                result = parse_json(saved["content"])
                if (
                    saved.get("finish_reason") == "stop"
                    and sorted(result.get("reviewed_ids", [])) == expected_ids
                    and isinstance(result.get("duplicates"), list)
                ):
                    return result
            except (ValueError, KeyError, TypeError):
                pass
            invalid = self.root / "rejected/call_cache" / (path.name + f".{time.time_ns()}.invalid")
            invalid.parent.mkdir(parents=True, exist_ok=True)
            path.replace(invalid)
        response, attempts = complete_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": instruction + "\n" + json.dumps(payload, ensure_ascii=False)}],
                max_completion_tokens=4096,
                reasoning_effort="low",
                extra_headers={"api-key": self.key},
            ),
            activity=self.activity,
            job_id=job_id,
        )
        content = response.choices[0].message.content or ""
        result = parse_json(content)
        if (
            response.choices[0].finish_reason != "stop"
            or sorted(result.get("reviewed_ids", [])) != expected_ids
            or not isinstance(result.get("duplicates"), list)
        ):
            write_json(
                self.root / "rejected/call_cache" / (job_id + f".{time.time_ns()}.json"),
                {"content": content, "reason": "Invalid novelty-review response"},
            )
            raise ValueError("Incomplete novelty review")
        write_json(
            path,
            {
                "content": content,
                "finish_reason": "stop",
                "context_pages": [],
                "requested_model": self.model,
                "returned_model": response.model,
                "transport_attempts": attempts,
            },
        )
        return result

    def run_job(self, document_id, slots, round_index, job_index):
        if len(slots) != 1:
            raise ValueError("The hybrid recipe uses one assigned QA per generation request")
        slot = slots[0]
        doc = self.docs[document_id]
        context = self._contexts.setdefault(document_id, prepare_context(self.root, doc))
        digest = hashlib.sha256(json.dumps(slot, sort_keys=True).encode()).hexdigest()[:8]
        job = f"r{round_index:02d}_{document_id}_{job_index:02d}_{digest}_hybrid_v1"
        use_window = slot["kind"] in {"single", "multi_local"} or (
            slot["kind"] == "reasoning" and slot["needle_count"] == 1
        )
        if use_window:
            trace_path = self.root / "calls" / (job + "_generate.json")
            generated = generate_window(
                self.client, self.key, self.model, context, doc, slot, job, trace_path, activity=self.activity
            )
            row = generated["candidate"]
            teacher_pages = generated["generation_pages"]
            text_pages = []  # The released generator receives page images, not extracted-text tool output.
            method = "released_prompt_window_v1"
            round_count, tool_count = 1, 0
        else:
            if document_id not in self._agents:
                self._agents[document_id] = DocumentAgent(
                    self.client,
                    self.key,
                    self.model,
                    context,
                    self.root / "agent_traces",
                    max_turns=self.disk_policy.get("agent_max_turns", 16),
                    max_tools=self.disk_policy.get("agent_max_tools", 32),
                    activity=self.activity,
                )
            existing = [
                json.loads(p.read_text())["question"] for p in (self.root / "accepted").glob(document_id + "_*.json")
            ]
            failures = sorted((self.root / "rejected").glob(slot["id"] + "_r*.json"), key=lambda p: p.stat().st_mtime)
            feedback = [json.loads(failures[-1].read_text()).get("rejection_reasons")] if failures else []
            row, generated = self._agents[document_id].generate(slot, job, existing, feedback)
            trace_path = self.root / "agent_traces" / (job + ".json")
            if row is None or row.get("status") != "candidate":
                self.reject(
                    slot, round_index, row, "Agent did not establish a qualified candidate within its tool budget"
                )
                return
            row = dict(row, slot=slot, document_id=document_id)
            teacher_pages = generated["image_pages_observed"]
            text_pages = generated["text_pages_observed"]
            method = "document_tool_agent_v1"
            round_count = len(generated["model_rounds"]) - generated.get("current_task_round_start", 0)
            tool_count = len(generated["tools"]) - generated.get("current_task_tool_start", 0)
        effective_slot = row["slot"]
        verification_path = self.root / "calls" / (job + "_verify.json")
        verified = full_document_review(
            self.client, self.key, self.model, doc, context / "pages", [row], verification_path, activity=self.activity
        )
        review = verified["result"]["reviews"][0]
        if not review_qualified(review, effective_slot, doc["page_count"]):
            self.reject(slot, round_index, row, review.get("reason", "Independent verification failed"), review)
            return
        second = full_document_review(
            self.client,
            self.key,
            self.model,
            doc,
            context / "pages",
            [row],
            self.root / "calls" / (job + "_verify_secondary.json"),
            activity=self.activity,
        )
        second_review = second["result"]["reviews"][0]
        if not review_qualified(second_review, effective_slot, doc["page_count"]):
            self.reject(
                slot, round_index, row, second_review.get("reason", "Second full-PDF check failed"), second_review
            )
            return
        if use_window:
            row["evidence_facts"] = review.get("verified_evidence_facts", [])
            row["evidence_annotation_source"] = "independent full-document verifier"
            if effective_slot["kind"] == "reasoning":
                row["calculation"] = canonical_calculation(review.get("verified_calculation", {}))
        if effective_slot["kind"] == "reasoning":
            value = numeric_answer(row["answer"])
            if value is None:
                self.reject(slot, round_index, row, "Reasoning answer is not one numeric quantity", review)
                return
            row["numeric_answer"] = value
        errors = validate(row, effective_slot, doc)
        if errors:
            self.reject(slot, round_index, row, errors, review)
            return
        row.update(
            source_url=doc["source_url"],
            license=doc["license"],
            license_url=doc["license_url"],
            context_sha256=doc["sha256"],
            context_page_count=doc["page_count"],
            page_indexing="zero-based PDF page index",
            teacher_pages=teacher_pages,
            generation_text_pages=text_pages,
            generation_method=method,
            planned_needle_count=slot["needle_count"],
            generation_full_document_available=not use_window or teacher_pages == list(range(doc["page_count"])),
            generation_model_turns=round_count,
            generation_tool_calls=tool_count,
            generation_trace=str(trace_path.relative_to(self.root.parent.parent)),
            verification=review,
            verification_context_pages=list(range(doc["page_count"])),
            verification_secondary=second_review,
            verification_policy="two_independent_full_pdf_checks",
            verification_method=f"independent {self.model} full-PDF audit with operation/type checks",
            generation_call=job + "_generate" if use_window else job,
            verification_call=job + "_verify",
            model=self.model,
            evidence_page_span=evidence_span(row["evidence_pages"], doc["page_count"]),
            actual_distance_bin=distance_bin(row["evidence_pages"], doc["page_count"])
            if row["evidence_pages"]
            else None,
        )
        question_key = re.sub(r"\W+", "", row["question"].casefold())
        with self.accept_lock:
            if question_key in self.question_keys:
                self.reject(slot, round_index, row, "Duplicate question")
                return
            write_json(self.root / "accepted" / (row["id"] + ".json"), row)
            self.question_keys.add(question_key)
        print("ACCEPTED_HYBRID", row["id"], method, flush=True)
