"""Recheck non-English/uncertain language predictions after removing equation lines.

Uses byte-range requests into the immutable source-PDF tar archives. Every fetched
PDF is checked against its recorded SHA-256. No PDF files are retained locally.
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path


def prose_text(text):
    text = unicodedata.normalize("NFKC", text)
    kept = []
    for line in text.splitlines():
        words = re.findall(r"[^\W\d_]{2,}", line, re.UNICODE)
        cjk = sum("\u3400" <= ch <= "\u9fff" for ch in line)
        if (len(words) >= 5 and sum(map(len, words)) >= 25) or cjk >= 15:
            kept.append(" ".join(words) if cjk < 15 else line)
    return "\n".join(kept)


def review_one(task):
    import fitz
    import requests
    from langid.langid import LanguageIdentifier, model

    label, document, member, base_url = task
    start, size = member["offset"], member["size"]
    for attempt in range(4):
        try:
            with requests.get(
                base_url + member["archive"],
                headers={"Range": f"bytes={start}-{start + size - 1}"},
                stream=True,
                timeout=(20, 90),
            ) as response:
                response.raise_for_status()
                if response.status_code != 206:
                    raise ValueError("Server did not honor byte range for " + document["id"])
                data = response.content
            break
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(type(exc).__name__ + ": " + document["id"]) from None
            time.sleep(2 ** (attempt + 1))
    if len(data) != size or hashlib.sha256(data).hexdigest() != document["sha256"]:
        raise ValueError("Ranged PDF checksum mismatch: " + document["id"])
    with fitz.open(stream=data, filetype="pdf") as pdf:
        text = "\n".join(pdf[p].get_text("text")[:10000] for p in label["language_sampled_pages"])
    text = prose_text(text)
    letters = sum(ch.isalpha() for ch in text)
    code, score = (
        ("und", None) if letters < 200 else LanguageIdentifier.from_modelstring(model, norm_probs=True).classify(text)
    )
    if score is not None and score < 0.9:
        code = "und"
    result = dict(label)
    result.update(
        language_initial_prediction=label["document_language"],
        language_initial_score=label["language_model_score"],
        document_language=code,
        language_model_score=None if score is None else float(score),
        language_status="prose_rechecked" if code != "und" else "uncertain_after_prose_recheck",
        language_prose_letters=letters,
        language_method=label["language_method"]
        + "; non-English/uncertain prediction rechecked on NFKC-normalized prose lines, excluding short equation-like lines",
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--input-labels", type=Path, required=True)
    parser.add_argument("--output-labels", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--repo-id", default="ZhaoweiWang/MMProLong-public-5B")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    labels = {r["document_id"]: r for line in args.input_labels.read_text().splitlines() if (r := json.loads(line))}
    documents = {
        d["id"]: d
        for line in (args.snapshot_root / "metadata/documents.jsonl").read_text().splitlines()
        if (d := json.loads(line))
    }
    offsets, members = {}, {}
    with gzip.open(args.snapshot_root / "metadata/asset_members.jsonl.gz", "rt") as stream:
        for line in stream:
            member = json.loads(line)
            if not member["archive"].startswith("archives/sources-"):
                continue
            # Source members are short ASCII names with ordinary-sized regular files;
            # their deterministic PAX tar representation uses one 512-byte header.
            if len(member["path"].encode("ascii")) > 100 or member["size"] >= 8**11:
                raise ValueError("Unsupported tar header layout")
            offset = offsets.get(member["archive"], 0)
            members[Path(member["path"]).stem] = {**member, "offset": offset + 512}
            offsets[member["archive"]] = offset + 512 + ((member["size"] + 511) // 512) * 512
    selected = [r for r in labels.values() if r["document_language"] != "en" or r["language_status"] != "detected"]
    base_url = f"https://huggingface.co/datasets/{args.repo_id}/resolve/{args.revision}/"
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        tasks = [(r, documents[r["document_id"]], members[r["document_id"]], base_url) for r in selected]
        for i, result in enumerate(pool.map(review_one, tasks), 1):
            labels[result["document_id"]] = result
            print(
                "RECHECKED",
                i,
                "/",
                len(selected),
                result["document_id"],
                result["language_initial_prediction"],
                "->",
                result["document_language"],
                flush=True,
            )
    args.output_labels.parent.mkdir(parents=True, exist_ok=True)
    with args.output_labels.open("w") as stream:
        for ident in sorted(labels):
            stream.write(json.dumps(labels[ident], ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
