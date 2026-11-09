# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 36,001 QA examples, 6,452 source PDFs, 148,826 unique page images, and 2,173,240,659 estimated training tokens (approximately 2.173B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/17c37b6e12882da04af048143580f9ca9325c6bf); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 6,452 |
| Document family | Public research papers |
| Unique rendered page images | 148,826 |
| Document pages: mean / median | 23.07 / 21 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-40 |
| Admitted QA examples | 36,001 |
| Estimated training tokens | 2,173,240,659 (2.173B) |
| Per-QA tokens: mean / median | 60.366K / 53.338K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,609 (7.25%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,189 (6.08%) |
| Page references across all QA contexts | 855,407 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 2,046 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 13,041 | 23.63 | 60.02 | 0.783 | 14-50 | 33.80-125.13 | 6.03% |
| `multi_local` | 6,441 | 23.82 | 60.60 | 0.390 | 14-50 | 33.85-125.50 | 6.04% |
| `multi_distributed` | 6,497 | 23.70 | 60.24 | 0.391 | 14-50 | 33.84-125.29 | 6.08% |
| `reasoning` | 6,503 | 23.70 | 60.18 | 0.391 | 14-50 | 33.55-125.11 | 5.80% |
| `unanswerable` | 3,519 | 24.34 | 61.80 | 0.217 | 14-50 | 33.79-125.09 | 6.88% |
| **Total** | 36,001 | 23.76 | 60.37 | 2.173 | 14-50 | 33.55-125.50 | 6.08% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,321 | 20.47% | 9,282 | 25.78% |
| Mathematics | 1,226 | 19.00% | 8,806 | 24.46% |
| Computer Science | 1,194 | 18.51% | 9,055 | 25.15% |
| Biology | 525 | 8.14% | 1,124 | 3.12% |
| Medicine | 487 | 7.55% | 1,264 | 3.51% |
| Social Science | 470 | 7.28% | 1,347 | 3.74% |
| Economics | 453 | 7.02% | 1,319 | 3.66% |
| Engineering | 447 | 6.93% | 2,815 | 7.82% |
| Earth Science | 310 | 4.80% | 892 | 2.48% |
| Language and Literature | 11 | 0.17% | 41 | 0.11% |
| Other | 8 | 0.12% | 56 | 0.16% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,427 | 15.07% |
| Float | 2,126 | 5.91% |
| List | 12,205 | 33.90% |
| String | 12,724 | 35.34% |
| Unanswerable | 3,519 | 9.77% |

There are **32,482 answerable** and **3,519 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,519, 1 pages: 16,397, 2 pages: 10,812, 3 pages: 4,184, 4 pages: 1,084, 5 pages: 3, 6 pages: 1, 7 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 613 |
| 2 | 3,432 |
| 6 | 1 |
| 8 | 1 |
| 9 | 7 |
| 10 | 51 |
| 11 | 259 |
| 12 | 2,084 |
| 20 | 4 |

The 20-QA documents belong to the initial pilot; the two-QA limit applies to the current GPT-5.6 phase.

</details>

### Generation methods

| Recorded method | QA |
| --- | --- |
| legacy_full_document | 32,432 |
| released_prompt_window_v1 | 2,227 |
| document_tool_agent_v1 | 1,342 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 1,948 |
| Crossref subject-query sampling; provisional until generator topic vote | 52 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 6,447 | 99.923% | 35,961 |
| Spanish (`es`) | 2 | 0.031% | 14 |
| French (`fr`) | 1 | 0.015% | 2 |
| Russian (`ru`) | 1 | 0.015% | 12 |
| Chinese (`zh`) | 1 | 0.015% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 79.23% | 1.745 |
| `gpt-5.6-sol` | 4,045 | 7,477 | 20.77% | 0.429 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 4,045 | 7,477 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
