"""Reproduce MMProLong public-corpus statistics, document labels, and figures.

Input is a downloaded snapshot with corpus.jsonl.gz, metadata/documents.jsonl,
and data/train-00000-of-00001.parquet. No PDF/image restoration is needed.
Requires numpy, pyarrow, and matplotlib. Language labels are produced separately
by annotate_public_document_languages.py, using the verified source PDFs.
"""

import argparse
import gzip
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


KINDS = ["single", "multi_local", "multi_distributed", "reasoning", "unanswerable"]
NAMES = {
    "single": "Single-page extraction",
    "multi_local": "Local multi-page extraction",
    "multi_distributed": "Distributed multi-page extraction",
    "reasoning": "Reasoning",
    "unanswerable": "Unanswerable",
}
TOKEN_EDGES = [32000, 48000, 64000, 80000, 96000, 112000, 128000]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def summarize(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"count": 0}
    return {
        "count": len(a),
        "min": float(a.min()),
        "max": float(a.max()),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "p05": float(np.quantile(a, 0.05)),
        "p95": float(np.quantile(a, 0.95)),
        "sum": float(a.sum()),
    }


def evidence_metrics(row, page_count):
    pages = row["evidence_pages"]
    if not pages:
        return {"evidence_page_count": 0, "evidence_span_normalized": None, "evidence_distance_bin": "no_evidence"}
    if len(set(pages)) != len(pages) or any(not 0 <= p < page_count for p in pages):
        raise ValueError("Invalid evidence pages: " + row["id"])
    span = (max(pages) - min(pages)) / (page_count - 1) if page_count > 1 else 0.0
    return {
        "evidence_page_count": len(pages),
        "evidence_span_normalized": span,
        "evidence_distance_bin": "near" if span <= 0.2 else "medium" if span <= 0.5 else "far",
    }


def task_stats(rows, documents):
    tokens = [r["token_count"] for r in rows]
    pages = [documents[r["document_id"]]["page_count"] for r in rows]
    return {
        "samples": len(rows),
        "documents": len({r["document_id"] for r in rows}),
        "pages": summarize(pages),
        "tokens": summarize(tokens),
        "tokens_ge_100000": sum(t >= 100000 for t in tokens),
        "tokens_ge_100000_percent": 100 * sum(t >= 100000 for t in tokens) / len(rows),
        "tokens_ge_102400": sum(t >= 102400 for t in tokens),
        "tokens_ge_102400_percent": 100 * sum(t >= 102400 for t in tokens) / len(rows),
    }


def build_profile(rows, documents, languages, snapshot_date="2026-11-08"):
    counts = Counter(r["document_id"] for r in rows)
    if set(counts) != set(documents):
        raise ValueError("Metadata must describe exactly the admitted document set")
    if languages is not None and set(languages) != set(documents):
        raise ValueError("Language labels must cover every admitted document")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate QA identifiers")
    for row in rows:
        doc = documents[row["document_id"]]
        if row["source_domain"] != doc["source_domain"]:
            raise ValueError("QA/document domain mismatch: " + row["id"])
        if row["context_sha256"] != doc["sha256"] or len(row["images"]) != doc["page_count"]:
            raise ValueError("QA/source metadata mismatch: " + row["id"])
    row_groups = {k: [r for r in rows if r["slot"]["kind"] == k] for k in KINDS}
    label_rows, extra_rows = [], []
    by_doc = defaultdict(list)
    for row in rows:
        by_doc[row["document_id"]].append(row)
    for ident, doc in sorted(documents.items()):
        group = by_doc[ident]
        lang = languages[ident] if languages is not None else {}
        label_rows.append(
            {
                "document_id": ident,
                "title": doc["title"],
                "source_url": doc["source_url"],
                "source_sha256": doc["sha256"],
                "source": doc["source"],
                "document_type": "arxiv_research_paper" if doc["source"] == "arxiv" else "unspecified",
                "source_domain": doc["source_domain"],
                "domain_tag_method": doc["domain_tag_method"],
                "document_language": lang.get("document_language", "und"),
                "language_status": lang.get("language_status", "not_assessed"),
                "language_model_score": lang.get("language_model_score"),
                "language_method": lang.get("language_method", "not_assessed"),
                "language_sampled_pages": lang.get("language_sampled_pages", []),
                "language_sampled_letters": lang.get("language_sampled_letters", 0),
                "page_count": doc["page_count"],
                "content_page_count": doc["content_page_count"],
                "document_image_tokens": sum(doc["image_tokens"]),
                "qa_count": len(group),
                "training_tokens": sum(r["token_count"] for r in group),
                "question_types": sorted({r["slot"]["kind"] for r in group}),
                "generation_models": sorted({r["model"] for r in group}),
                "source_license": doc["license"],
            }
        )
    for row in rows:
        doc = documents[row["document_id"]]
        phase = (
            "gpt56_two_qa"
            if row["model"] == "gpt-5.6-sol"
            else ("initial_pilot" if counts[row["document_id"]] == 20 else "gpt55_production")
        )
        extra_rows.append(
            {
                "id": row["id"],
                "document_page_count": doc["page_count"],
                "content_page_count": doc["content_page_count"],
                "document_type": "arxiv_research_paper" if doc["source"] == "arxiv" else "unspecified",
                "document_language": languages[row["document_id"]]["document_language"]
                if languages is not None
                else "und",
                "domain_tag_method": doc["domain_tag_method"],
                "generation_phase": phase,
                **evidence_metrics(row, doc["page_count"]),
            }
        )
    qa_domains, doc_domains = (
        Counter(r["source_domain"] for r in rows),
        Counter(d["source_domain"] for d in documents.values()),
    )
    domains = []
    for name, n in doc_domains.most_common():
        group = [r for r in rows if r["source_domain"] == name]
        domains.append(
            {
                "domain": name,
                "documents": n,
                "document_percent": 100 * n / len(documents),
                "samples": qa_domains[name],
                "sample_percent": 100 * qa_domains[name] / len(rows),
                "tokens": sum(r["token_count"] for r in group),
            }
        )
    by_model = []
    for name in sorted({r["model"] for r in rows}):
        group = [r for r in rows if r["model"] == name]
        by_model.append({"model": name, **task_stats(group, documents)})
    by_phase = []
    for phase in sorted({r["generation_phase"] for r in extra_rows}):
        group = [r for r, e in zip(rows, extra_rows, strict=True) if e["generation_phase"] == phase]
        by_phase.append(
            {
                "phase": phase,
                **task_stats(group, documents),
                "max_qa_per_document": max(Counter(r["document_id"] for r in group).values()),
            }
        )
    image_tokens = sum(sum(documents[r["document_id"]]["image_tokens"]) for r in rows)
    total_tokens = sum(r["token_count"] for r in rows)
    language_counts = Counter(d["document_language"] for d in label_rows)
    profile = {
        "snapshot_date": snapshot_date,
        "scope": "Admitted public QA only; unique documents versus repeated QA contexts are counted separately.",
        "overview": {
            "documents": len(documents),
            "samples": len(rows),
            "unique_page_images": sum(d["page_count"] for d in documents.values()),
            "qa_page_references": sum(documents[r["document_id"]]["page_count"] for r in rows),
            "estimated_training_tokens": total_tokens,
            "estimated_image_tokens_across_qa": image_tokens,
            "estimated_text_and_prompt_tokens_across_qa": total_tokens - image_tokens,
            "unique_document_image_tokens": sum(sum(d["image_tokens"]) for d in documents.values()),
        },
        "document_pages": summarize([d["page_count"] for d in documents.values()]),
        "content_pages": summarize([d["content_page_count"] for d in documents.values()]),
        "all_samples": task_stats(rows, documents),
        "by_kind": [{"kind": k, "name": NAMES[k], **task_stats(row_groups[k], documents)} for k in KINDS],
        "paper_aligned_task_groups": [
            {"name": name, **task_stats([r for r in rows if r["slot"]["kind"] in kinds], documents)}
            for name, kinds in [
                ("Single-page extraction", ["single"]),
                ("Multi-page extraction", ["multi_local", "multi_distributed"]),
                ("Reasoning", ["reasoning"]),
                ("Unanswerable (public extension)", ["unanswerable"]),
            ]
        ],
        "domains": domains,
        "domain_tag_methods": dict(Counter(d["domain_tag_method"] for d in documents.values())),
        "document_types": dict(Counter(d["document_type"] for d in label_rows)),
        "source_licenses": dict(Counter(d["license"] for d in documents.values())),
        "languages": [
            {
                "language": code,
                "documents": n,
                "document_percent": 100 * n / len(documents),
                "samples": sum(e["document_language"] == code for e in extra_rows),
            }
            for code, n in language_counts.most_common()
        ],
        "language_status": dict(Counter(d["language_status"] for d in label_rows)),
        "by_model": by_model,
        "sampling_phases": by_phase,
        "qa_per_document_histogram": {str(k): v for k, v in sorted(Counter(counts.values()).items())},
        "answer_formats": dict(Counter(r["answer_format"] for r in rows)),
        "answerability": {
            "answerable": sum(r["answerable"] for r in rows),
            "unanswerable": sum(not r["answerable"] for r in rows),
        },
        "evidence_page_counts": {
            str(k): v for k, v in sorted(Counter(e["evidence_page_count"] for e in extra_rows).items())
        },
        "evidence_distance_bins": dict(Counter(e["evidence_distance_bin"] for e in extra_rows)),
        "token_histogram": {
            "edges": TOKEN_EDGES,
            "counts": np.histogram([r["token_count"] for r in rows], TOKEN_EDGES)[0].tolist(),
        },
        "methodology": {
            "K": "1000 tokens in tables/plots; exact token values are also recorded",
            "B": "1000000000 tokens",
            "paper_prefixes": "The manuscript defines K=1024 and B=1073741824. Its 100K threshold is 102400; both 100000 and 102400 thresholds are reported here.",
            "pages_in_task_tables": "QA-weighted full-document page count",
            "document_domain_counts": "Unique admitted PDF documents; primary domain labels, not multi-label topics",
            "language": METHOD if languages is not None else "Not assessed in this preliminary run",
            "evidence_span": "(max(evidence_pages)-min(evidence_pages))/(document_page_count-1); absent evidence is null, not near",
            "evidence_distance": "near <= 0.2; medium > 0.2 and <= 0.5; far > 0.5; no_evidence for empty evidence",
            "token_metric": "Stored Qwen2.5-VL serialized training-sample estimate, including page images and QA/prompt text; repeated context counted per QA",
        },
    }
    return profile, label_rows, extra_rows


METHOD = "langid-1.1.6 on embedded text from up to six sampled body pages; initial non-English/uncertain predictions rechecked on normalized prose lines without short equation-like lines; no OCR; score < 0.9 or fewer than 200 letters -> und; automatic, not human-verified"


def figures(rows, documents, profile, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "savefig.facecolor": "white",
        }
    )
    color = "#236B8E"
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
    domains = profile["domains"][::-1]
    ax = axes[0, 0]
    bars = ax.barh([d["domain"] for d in domains], [d["documents"] for d in domains], color=color)
    ax.bar_label(bars, padding=4, fontsize=9)
    ax.set(xlabel="Unique PDF documents", title="Primary domain (document-weighted)")
    ax.set_xlim(0, max(d["documents"] for d in domains) * 1.18)
    ax = axes[0, 1]
    bars = ax.barh(
        ["Single-page", "Local multi-page", "Distributed multi-page", "Reasoning", "Unanswerable"][::-1],
        [p["samples"] for p in profile["by_kind"]][::-1],
        color=color,
    )
    ax.bar_label(bars, padding=4, fontsize=9)
    ax.set(xlabel="QA examples", title="Question type (QA-weighted)")
    ax.set_xlim(0, max(x["samples"] for x in profile["by_kind"]) * 1.18)
    ax = axes[1, 0]
    page_counts = [d["page_count"] for d in documents.values()]
    ax.hist(
        page_counts, bins=np.arange(min(page_counts) - 0.5, max(page_counts) + 1.5, 1), color=color, edgecolor="white"
    )
    ax.set(xlabel="Pages per unique PDF", ylabel="Documents", title="Document page-count distribution")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax = axes[1, 1]
    bars = ax.barh(
        [r["model"] for r in profile["by_model"]][::-1], [r["samples"] for r in profile["by_model"]][::-1], color=color
    )
    ax.bar_label(bars, padding=4, fontsize=9)
    ax.set(xlabel="QA examples", title="Generation model recorded per QA")
    ax.set_xlim(0, max(r["samples"] for r in profile["by_model"]) * 1.18)
    overview = profile["overview"]
    date = profile["snapshot_date"]
    fig.suptitle(
        f"MMProLong public corpus | {date} | {overview['documents']:,} documents / {overview['samples']:,} QA",
        fontsize=15,
    )
    fig.supxlabel(
        "Source: admitted public-corpus ledger and document metadata. This is a separately constructed public dataset.",
        fontsize=9,
    )
    fig.savefig(output / "public_corpus_overview.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 5, figsize=(19, 4.2), layout="constrained", sharex=True)
    short = ["Single-page extraction", "Local multi-page", "Distributed multi-page", "Reasoning", "Unanswerable"]
    for ax, k, label, stats in zip(axes, KINDS, short, profile["by_kind"], strict=True):
        values = [r["token_count"] / 1000 for r in rows if r["slot"]["kind"] == k]
        ax.hist(values, bins=np.arange(32, 129, 8), color=color, edgecolor="white")
        ax.axvline(102.4, color="#B15B2D", linestyle="--", linewidth=1.3, label="102,400 tokens")
        ax.set(title=label, xlabel="Estimated tokens (K)", ylabel="QA examples", xticks=[32, 64, 96, 128])
        ax.text(
            0.96,
            0.96,
            f"n = {stats['samples']:,}\nmean = {stats['tokens']['mean'] / 1000:.1f}K\n>=100Ki: {stats['tokens_ge_102400_percent']:.2f}%",
            ha="right",
            va="top",
            transform=ax.transAxes,
            fontsize=9,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.95, "pad": 3},
        )
    fig.suptitle(f"Full training-sample length by task | public snapshot {date}", fontsize=14)
    fig.supxlabel(
        "Axis K = 1,000; dashed line = 100Ki = 102,400 tokens (paper threshold). Qwen2.5-VL estimate includes complete page images and QA/prompt text.",
        fontsize=9,
    )
    fig.savefig(output / "token_length_by_task.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    positions = [p / (documents[r["document_id"]]["page_count"] - 1) for r in rows for p in r["evidence_pages"]]
    axes[0].hist(positions, bins=np.linspace(0, 1, 11), color=color, edgecolor="white")
    axes[0].set(
        xlabel="Evidence page / (document pages - 1)",
        ylabel="Cited necessary evidence pages",
        title="Evidence position in complete PDF",
    )
    counts = profile["evidence_distance_bins"]
    names = ["near", "medium", "far", "no_evidence"]
    bars = axes[1].bar(names, [counts.get(k, 0) for k in names], color=color)
    axes[1].bar_label(bars, padding=3)
    axes[1].set(
        xlabel="Actual normalized evidence span",
        ylabel="QA examples",
        title="Evidence distance, not sampling task label",
    )
    axes[1].set_ylim(0, max(counts.values()) * 1.18)
    fig.suptitle(f"Evidence annotations | public snapshot {date}", fontsize=14)
    fig.supxlabel(
        "Span = (last - first evidence page)/(PDF pages - 1). Near <=0.2; medium <=0.5; far >0.5. Empty evidence is kept separate.",
        fontsize=9,
    )
    fig.savefig(output / "evidence_distribution.png", dpi=180)
    plt.close(fig)


def main():
    import pyarrow as pa
    import pyarrow.parquet as pq

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--language-labels", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.snapshot_root / "corpus.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    documents = {
        d["id"]: d
        for line in (args.snapshot_root / "metadata/documents.jsonl").read_text().splitlines()
        if (d := json.loads(line))
    }
    languages = None
    if args.language_labels:
        languages = {
            r["document_id"]: r for line in args.language_labels.read_text().splitlines() if (r := json.loads(line))
        }
    snapshot = json.loads((args.snapshot_root / "metadata/snapshot.json").read_text())
    profile, labels, extras = build_profile(rows, documents, languages, snapshot["snapshot_date"])
    if profile["overview"]["samples"] != snapshot["accepted_samples"]:
        raise ValueError("Profile sample count differs from snapshot metadata")
    output = args.output_dir
    (output / "metadata").mkdir(parents=True, exist_ok=True)
    if args.language_labels:
        shutil.copyfile(args.language_labels, output / "metadata/document_languages.jsonl")
    dump(output / "metadata/statistics.json", profile)
    with (output / "metadata/document_labels.jsonl").open("w") as stream:
        for row in labels:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    pq.write_table(pa.Table.from_pylist(labels), output / "metadata/document_labels.parquet", compression="zstd")
    original = pq.read_table(args.snapshot_root / "data/train-00000-of-00001.parquet")
    by_id = {r.pop("id"): r for r in extras}
    extra_table = pa.Table.from_pylist([by_id[ident] for ident in original.column("id").to_pylist()])
    enriched = original
    for name in extra_table.column_names:
        if name in enriched.column_names:
            enriched = enriched.set_column(enriched.schema.get_field_index(name), name, extra_table.column(name))
        else:
            enriched = enriched.append_column(name, extra_table.column(name))
    core_columns = [name for name in original.column_names if name not in extra_table.column_names]
    assert enriched.select(core_columns).equals(original.select(core_columns))
    (output / "data").mkdir(exist_ok=True)
    pq.write_table(enriched, output / "data/train-00000-of-00001.parquet", compression="zstd")
    figures(rows, documents, profile, output / "assets")
    print(
        json.dumps(
            {"overview": profile["overview"], "languages": profile["languages"], "domain_coverage": len(labels)}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
