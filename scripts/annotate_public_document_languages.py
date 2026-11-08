"""Label document language from verified PDF archives without restoring the corpus.

Requires pymupdf, langid==1.1.6, numpy, and requests. Each worker holds at most
one archive in memory. Only labels and resumable checkpoints are written to disk.
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import tarfile
import time
from pathlib import Path


os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

METHOD = "langid-1.1.6 on embedded PDF text from up to six sampled body pages; no OCR; automatic, not human-verified"
IDENTIFIER = None


def identify_document(pdf_bytes, document):
    import fitz
    from langid.langid import LanguageIdentifier, model

    global IDENTIFIER
    if IDENTIFIER is None:
        IDENTIFIER = LanguageIdentifier.from_modelstring(model, norm_probs=True)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    if digest != document["sha256"]:
        raise ValueError("PDF checksum mismatch: " + document["id"])
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        if len(pdf) != document["page_count"]:
            raise ValueError("PDF page count mismatch: " + document["id"])
        body = min(len(pdf), document.get("content_page_count", len(pdf)))
        pages = sorted({p for p in [0, 1, 2, body // 3, 2 * body // 3, body - 1] if 0 <= p < body})
        texts = [pdf[p].get_text("text")[:10000] for p in pages]
    text = "\n".join(texts)
    letters = sum(ch.isalpha() for ch in text)
    language, score = ("und", None) if letters < 200 else IDENTIFIER.classify(text)
    status = "insufficient_embedded_text" if letters < 200 else "detected"
    if score is not None and score < 0.9:
        language, status = "und", "low_classifier_score"
    return {
        "document_id": document["id"],
        "document_language": language,
        "language_model_score": None if score is None else float(score),
        "language_status": status,
        "language_method": METHOD,
        "language_sampled_pages": pages,
        "language_sampled_letters": letters,
        "source_sha256": digest,
    }


def annotate_archive(task):
    import requests

    archive, documents, base_url = task
    for attempt in range(5):
        try:
            with requests.get(base_url + archive["path"], timeout=(20, 180)) as response:
                response.raise_for_status()
                payload = response.content
            break
        except requests.RequestException as exc:
            if attempt == 4:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                raise RuntimeError(f"{type(exc).__name__}: HTTP {code}: {archive['path']}") from None
            time.sleep(min(30, 2 ** (attempt + 1)))
    if len(payload) != archive["size"] or hashlib.sha256(payload).hexdigest() != archive["sha256"]:
        raise ValueError("Archive checksum mismatch: " + archive["path"])
    labels = []
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".pdf"):
                continue
            ident = Path(member.name).stem
            if ident in documents:
                with tar.extractfile(member) as stream:
                    labels.append(identify_document(stream.read(), documents[ident]))
    return archive["path"], labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--revision", required=True, help="Pinned Hugging Face commit")
    parser.add_argument("--repo-id", default="ZhaoweiWang/MMProLong-public-5B")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.snapshot_root / "release_manifest.json").read_text())
    documents = {
        d["id"]: d
        for line in (args.snapshot_root / "metadata/documents.jsonl").read_text().splitlines()
        if (d := json.loads(line))
    }
    archives = [
        f for f in manifest["files"] if f["path"].startswith("archives/sources-") and f["path"].endswith(".tar")
    ]
    checkpoint = args.output_dir / "language_checkpoint.json"
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        if state["revision"] != args.revision:
            raise ValueError("Checkpoint belongs to a different revision")
    else:
        state = {"revision": args.revision, "archives": [], "documents": {}}
    pending = [a for a in archives if a["path"] not in state["archives"]]
    base_url = f"https://huggingface.co/datasets/{args.repo_id}/resolve/{args.revision}/"
    status = {
        "phase": "annotating_languages",
        "archives": len(state["archives"]),
        "total_archives": len(archives),
        "documents": len(state["documents"]),
        "total_documents": len(documents),
        "updated_at_unix": time.time(),
    }
    (args.output_dir / "language_status.json").write_text(json.dumps(status) + "\n")
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(annotate_archive, (a, documents, base_url)) for a in pending]
        for future in concurrent.futures.as_completed(futures):
            name, labels = future.result()
            state["archives"].append(name)
            for label in labels:
                state["documents"][label["document_id"]] = label
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, ensure_ascii=False) + "\n")
            temporary.replace(checkpoint)
            status = {
                "phase": "annotating_languages",
                "archives": len(state["archives"]),
                "total_archives": len(archives),
                "documents": len(state["documents"]),
                "total_documents": len(documents),
                "updated_at_unix": time.time(),
            }
            (args.output_dir / "language_status.json").write_text(json.dumps(status) + "\n")
            print(json.dumps(status), flush=True)
    if set(state["documents"]) != set(documents):
        raise ValueError("Language-label coverage does not match the admitted document set")
    with (args.output_dir / "document_languages.jsonl").open("w") as output:
        for ident in sorted(documents):
            output.write(json.dumps(state["documents"][ident], ensure_ascii=False) + "\n")
    status["phase"] = "complete"
    (args.output_dir / "language_status.json").write_text(json.dumps(status) + "\n")


if __name__ == "__main__":
    main()
