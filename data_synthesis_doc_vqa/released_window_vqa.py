"""Adapter around the released window sampler and few-shot generation prompt.

Only source-input preparation and OpenAI-compatible image transport are adapted;
the released prompt builder is called directly. Training context stays complete.
"""

import hashlib
import importlib.util
import json
import random
import re
import threading
from pathlib import Path

from api_parse_utils import parse_qa_pair_output
from public_vqa_pipeline import write_json


_BUILD_LOCK = threading.Lock()
_PDF_LOCK = threading.Lock()
_RELEASED = None
_EXEMPLARS = None


def ensure_symlink(path, target, directory=False):
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise ValueError("Existing context link points to a different source")
    elif path.exists():
        raise ValueError("Unexpected existing context asset")
    else:
        path.symlink_to(target.resolve(), target_is_directory=directory)


def prepare_context(batch, document):
    import fitz

    batch = Path(batch)
    root = batch / "agent_context" / document["id"]
    root.mkdir(parents=True, exist_ok=True)
    source = batch / "sources" / (document["id"] + ".pdf")
    if (root / "page_text.json").exists() and (root / "document.json").exists():
        old = json.loads((root / "document.json").read_text())
        if old["sha256"] != document["sha256"]:
            raise ValueError("Cached document context changed")
        return root
    if hashlib.sha256(source.read_bytes()).hexdigest() != document["sha256"]:
        raise ValueError("Document source hash mismatch")
    ensure_symlink(root / "pages", batch / "images" / document["id"], directory=True)
    ensure_symlink(root / "document.pdf", source)
    texts, layout = [], []
    # PyMuPDF is not thread safe; API workers may prepare different PDFs concurrently.
    with _PDF_LOCK, fitz.open(source) as pdf:
        outline = pdf.get_toc()
        for index, page in enumerate(pdf):
            text = page.get_text()
            texts.append({"page": index, "text": text})
            titles = [title for _, title, number in outline if number - 1 == index]
            for line in text.splitlines():
                clean = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s+", "", line).strip()
                if re.fullmatch(
                    r"Abstract|Introduction|Background|Results(?: and discussion)?|Discussion|Conclusions?|Materials and methods|Methods|Methodology|Author summary|Supporting information|References|Acknowledg[e]?ments",
                    clean,
                    re.I,
                ):
                    titles.append(line.strip())
            layout.append(
                {
                    "page_id": index,
                    "page_blocks": json.dumps([{"label": "sec", "text": title} for title in dict.fromkeys(titles)]),
                }
            )
    source_name, ident = document["source"], document["id"]
    image_dir = root / "legacy_images" / source_name / ident[:1]
    image_dir.mkdir(parents=True, exist_ok=True)
    for index in range(document["page_count"]):
        destination = image_dir / f"{source_name}__{ident}_page{index}.png"
        ensure_symlink(destination, batch / "images" / ident / f"page{index:03d}.png")
    write_json(root / "legacy_ocr" / source_name / (ident + ".json"), layout)
    write_json(root / "document.json", document)
    write_json(root / "page_text.json", texts)
    return root


def released_inputs(context, document, kind, seed):
    global _RELEASED, _EXEMPLARS
    from huggingface_hub import hf_hub_download
    from prompt_utils import extract_prompt_template_dict, math_prompt_template_dict

    with _BUILD_LOCK:
        if _RELEASED is None:
            path = Path(__file__).with_name("3_prompt_API_for_long_vqa_data.py")
            spec = importlib.util.spec_from_file_location("released_vqa_generation", path)
            _RELEASED = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_RELEASED)
        if _EXEMPLARS is None:
            path = hf_hub_download(
                "dengchao/LongDocURL", "LongDocURL_public_with_subtask_category.jsonl", repo_type="dataset"
            )
            _EXEMPLARS = [json.loads(line) for line in Path(path).read_text().splitlines()]
        if kind == "reasoning":
            template = math_prompt_template_dict
            restriction = template["extra_all_page_restriction"]
            examples = [r for r in _EXEMPLARS if r["question_type"] in {"calculate", "compare", "count"}]
        else:
            template = extract_prompt_template_dict
            flag = "single" if kind == "single" else "multi"
            restriction = template[f"extra_{flag}_page_restriction"]
            examples = [
                r
                for r in _EXEMPLARS
                if r["question_type"] == "extract"
                and (len(r["evidence_pages"]) == 1 if kind == "single" else len(r["evidence_pages"]) > 1)
            ]
        _RELEASED._detailed_task_description = template["detailed_task_description"]
        _RELEASED._extra_page_restriction = restriction
        _RELEASED._exemplar_data = examples
        state = random.getstate()
        try:
            for attempt in range(30):
                random.seed(seed + attempt)
                prompt, _, images, pages = _RELEASED.build_example_prompt(
                    document, 2, str(context / "legacy_images"), str(context / "legacy_ocr")
                )
                if 8 <= len(pages) <= 15 and sum(p < document["content_page_count"] for p in pages) >= 8:
                    return prompt, images, pages
            raise ValueError("No eligible released-style window with eight body pages")
        finally:
            random.setstate(state)


def numeric_answer(answer):
    if isinstance(answer, (float, int)) and not isinstance(answer, bool):
        return float(answer)
    match = re.fullmatch(r"\s*[$€£]?\s*([-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*[^\d]*", str(answer))
    return float(match[1].replace(",", "")) if match else None


def canonical_calculation(calculation):
    result = dict(calculation)
    aliases = {
        "addition": "+",
        "sum": "+",
        "subtraction": "-",
        "subtract": "-",
        "multiplication": "*",
        "product": "*",
        "division": "/",
        "divide": "/",
        "maximum": "max",
        "minimum": "min",
    }
    operator = str(result.get("operator", "")).strip()
    result["operator"] = aliases.get(operator.casefold(), operator)
    return result


def generate_window(client, key, model, context, document, slot, job_id, output_path, activity=None):
    from agentic_vqa import complete_with_retry

    output_path = Path(output_path)
    if output_path.exists():
        saved = json.loads(output_path.read_text())
        if saved["context_sha256"] != document["sha256"]:
            raise ValueError("Window generation cache belongs to another document")
        return saved
    seed = int(hashlib.sha256(job_id.encode()).hexdigest()[:8], 16)
    prompt, images, pages = released_inputs(context, document, slot["kind"], seed)
    # This calls the released formatter; normalize only the image transport shape.
    messages = _RELEASED.convert_to_chat_format(prompt, images)
    for block in messages[0]["content"]:
        if block["type"] == "image_url" and isinstance(block["image_url"], str):
            block["image_url"] = {"url": block["image_url"], "detail": "high"}
    from lossless_transport import optimize_blocks

    optimize_blocks(messages, output_path.parent.parent / "transport_cache")
    response, attempts = complete_with_retry(
        lambda: client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=16000,
            reasoning_effort="medium",
            extra_headers={"api-key": key},
        ),
        activity=activity,
        job_id=job_id,
    )
    if response.choices[0].finish_reason != "stop":
        raise ValueError("Incomplete original-window generation")
    content = response.choices[0].message.content or ""
    parsed = parse_qa_pair_output(content)
    qa = parsed["qa_json"]
    evidence = qa.get("evidence_pages")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(type(p) is not int or p not in pages or p >= document["content_page_count"] for p in evidence)
    ):
        raise ValueError("Evidence is outside the supplied content window")
    if (
        len(set(evidence)) != len(evidence)
        or (slot["kind"] == "single" and len(evidence) != 1)
        or (slot["kind"] == "multi_local" and len(evidence) < 2)
    ):
        raise ValueError("Generation did not satisfy the intended single/multi evidence count")
    effective_slot = dict(
        slot,
        allowed_evidence_pages=[p for p in pages if p < document["content_page_count"]],
        needle_count=len(evidence),
        generation_sampling="released_section_window",
    )
    if slot["kind"] == "multi_local":
        effective_slot["local_window"] = [pages[0], pages[-1]]
    candidate = dict(
        qa,
        id=slot["id"],
        slot=effective_slot,
        document_id=document["id"],
        answerable=True,
        evidence_description=parsed["qa_evidence_description"],
        evidence_facts=[],
        calculation={},
        related_context_pages=[],
        missing_information="",
    )
    if slot["kind"] == "reasoning":
        value = numeric_answer(qa["answer"])
        if value is None:
            raise ValueError("Reasoning answer is not a single numeric quantity")
        candidate["numeric_answer"] = value
    result = {
        "candidate": candidate,
        "content": content,
        "context_sha256": document["sha256"],
        "generation_pages": pages,
        "generation_method": "released_prompt_window_v1",
        "sampling_seed": seed,
        "requested_model": model,
        "returned_model": response.model,
        "transport_attempts": attempts,
        "usage": response.usage.model_dump() if response.usage else {},
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "released_script_sha256": hashlib.sha256(
            Path(__file__).with_name("3_prompt_API_for_long_vqa_data.py").read_bytes()
        ).hexdigest(),
        "few_shot_source": "dengchao/LongDocURL/LongDocURL_public_with_subtask_category.jsonl",
        "few_shot_count": 2,
    }
    write_json(output_path, result)
    return result
