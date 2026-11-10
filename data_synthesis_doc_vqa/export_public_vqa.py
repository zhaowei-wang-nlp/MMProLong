"""Export only fully verified public QA; preserve complete PDF page order."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from api_parse_utils import item_template, system_template, user_template
from PIL import Image
from public_vqa_pipeline import COUNTS, review_passes, validate, write_json
from transformers import AutoProcessor


def export(root):
    documents = {d["id"]: d for d in json.loads((root / "manifest.json").read_text())}
    rows = [json.loads(p.read_text()) for p in sorted((root / "accepted").glob("*.json"))]
    counts = Counter(r["slot"]["kind"] for r in rows)
    if counts != COUNTS:
        raise ValueError(f"Incomplete batch: {dict(counts)}")
    spec = importlib.util.spec_from_file_location(
        "original_formatter", Path(__file__).with_name("4_postprocess_VeOmni_format.py")
    )
    formatter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(formatter)
    processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct", use_fast=False)
    patch, merge = processor.image_processor.patch_size, processor.image_processor.merge_size
    task_map = {
        "single": ("extract", "single_page"),
        "multi_local": ("extract", "multi_page"),
        "multi_distributed": ("extract", "multi_page"),
        "reasoning": ("math", "all_page"),
        "unanswerable": ("unanswerable", "all_page"),
    }
    output_rows = []
    for doc_id, doc in documents.items():
        pdf_path = root / "sources" / (doc_id + ".pdf")
        if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != doc["sha256"]:
            raise ValueError("Document changed after verification")
        image_list = []
        for i in range(doc["page_count"]):
            path = root / "images" / doc_id / f"page{i:03d}.png"
            with Image.open(path) as im:
                image_list.append({"url": str(path), "width": im.width, "height": im.height, "page_id": i})
        for kind, (question_type, page_flag) in task_map.items():
            current = [r for r in rows if r["document_id"] == doc_id and r["slot"]["kind"] == kind]
            if not current:
                continue
            converted = []
            for r in current:
                assert not validate(r, r["slot"], doc)
                assert review_passes(r["verification"], r["slot"], doc["page_count"])
                assert r["verification_context_pages"] == list(range(doc["page_count"]))
                answer = r["answer"] if isinstance(r["answer"], str) else json.dumps(r["answer"], ensure_ascii=False)
                context = "\n\n".join(item_template.format(doc_id=doc_id, page_id=i) for i in range(doc["page_count"]))
                text = user_template.format(question=r["question"], context=context)
                chat = [
                    {"role": "user", "content": formatter.format_chat(text, image_list)},
                    {"role": "assistant", "content": [{"type": "text", "text": system_template + " " + answer}]},
                ]
                tokens = formatter.compute_prompt_length(chat, processor.tokenizer, patch, merge)
                if not 32768 <= tokens <= 126976:
                    raise ValueError(f"Context outside limits: {r['id']} ({tokens}). Do not silently truncate it.")
                fmt = {
                    "global_id": doc_id,
                    "qa_json": {"question": r["question"], "answer": answer},
                    "public_id": r["id"],
                    "source": "arxiv",
                    "page_count": doc["page_count"],
                    "evidence_pages": r["evidence_pages"],
                    "kind": kind,
                    "answerable": r["answerable"],
                    "context_sha256": doc["sha256"],
                    "source_url": doc["source_url"],
                    "license": doc["license"],
                    "license_url": doc["license_url"],
                    "token_count": tokens,
                }
                formatter._question_type, formatter._page_flag = question_type, page_flag
                fmt = formatter.convert_to_llava_format(fmt, chat)
                fmt["qa_json"] = json.dumps(fmt["qa_json"], ensure_ascii=False)
                fmt["source_name"] = "mmprolong_public_" + kind
                assert len(fmt["images"]) == doc["page_count"]
                assert sum(t["value"].count("<image>") for t in json.loads(fmt["conversations"])) == len(fmt["images"])
                converted.append(fmt)
                r["token_count"] = tokens
                r["category"] = (
                    "single_needle" if kind == "single" else "multi_needle" if kind.startswith("multi_") else kind
                )
                r["multi_needle_scope"] = kind.removeprefix("multi_") if kind.startswith("multi_") else None
                image_tokens = doc["image_tokens"]
                r["evidence_page_positions"] = [round(p / (doc["page_count"] - 1), 6) for p in r["evidence_pages"]]
                r["evidence_token_positions_estimated"] = [
                    round((sum(image_tokens[:p]) + image_tokens[p] / 2) / sum(image_tokens), 6)
                    for p in r["evidence_pages"]
                ]
                r["token_position_method"] = (
                    "Qwen2.5-VL page-image token estimate, page centers, normalized over all page images"
                )
                r["context_page_ids"] = list(range(doc["page_count"]))
                r["parquet"] = f"training/{kind}/{doc_id}.parquet"
                output_rows.append(r)
            path = root / "training" / kind / (doc_id + ".parquet")
            path.parent.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(converted)
            # Keep the same schema for unanswerable shards whose evidence lists
            # are all empty; otherwise Arrow infers list<null> for those shards.
            index = table.schema.get_field_index("evidence_pages")
            table = table.set_column(
                index, "evidence_pages", pa.array([r["evidence_pages"] for r in converted], type=pa.list_(pa.int64()))
            )
            temporary = path.with_suffix(".parquet.tmp")
            pq.write_table(table, temporary, compression="zstd", row_group_size=1)
            temporary.replace(path)
            print("EXPORTED", doc_id, kind, len(converted), flush=True)
    output_rows.sort(key=lambda r: r["id"])
    (root / "public_qa.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in output_rows))
    stats = {}
    for kind in COUNTS:
        selected = [r for r in output_rows if r["slot"]["kind"] == kind]
        spans = [(max(r["evidence_pages"]) - min(r["evidence_pages"])) for r in selected if r["evidence_pages"]]
        stats[kind] = {
            "count": len(selected),
            "actual_distance_bins": dict(Counter(r["actual_distance_bin"] for r in selected)),
            "page_span_min": min(spans) if spans else None,
            "page_span_max": max(spans) if spans else None,
            "needle_counts": dict(Counter(len(r["evidence_pages"]) for r in selected)),
        }
    calls = [json.loads(p.read_text()) for p in (root / "calls").glob("*.json")]
    summary = {
        "count": len(output_rows),
        "documents": len(documents),
        "source_pages": sum(d["page_count"] for d in documents.values()),
        "counts": dict(counts),
        "distribution": stats,
        "token_min": min(r["token_count"] for r in output_rows),
        "token_max": max(r["token_count"] for r in output_rows),
        "api_calls_with_saved_responses": len(calls),
        "usage_scope": "Returned usage only; failed or timed-out requests without responses are excluded",
        "usage": {
            k: sum((c.get("usage") or {}).get(k, 0) for c in calls)
            for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
        },
        "verification": "Separate GPT-5.5 audit using every final context page; not 100-item human validation",
        "unanswerable_subtypes": dict(
            Counter(r["slot"].get("subtype") for r in rows if r["slot"]["kind"] == "unanswerable")
        ),
        "limitations": [
            "benchmark PDF/URL decontamination pending",
            "GPU training ingestion not tested",
            "five technical survey documents; limited domain diversity",
            "automated verification can miss errors",
        ],
    }
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    export(parser.parse_args().root)
