# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 37,783 QA examples, 7,450 source PDFs, 169,520 unique page images, and 2,266,988,794 estimated training tokens (approximately 2.267B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/e3038ec88dcd8939afb35d8c41555d52ef2673d3); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 7,450 |
| Document family | Public research papers |
| Unique rendered page images | 169,520 |
| Document pages: mean / median | 22.75 / 21 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-39 |
| Admitted QA examples | 37,783 |
| Estimated training tokens | 2,266,988,794 (2.267B) |
| Per-QA tokens: mean / median | 60.000K / 53.296K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,618 (6.93%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,198 (5.82%) |
| Page references across all QA contexts | 892,361 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 3,044 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 13,689 | 23.49 | 59.64 | 0.816 | 14-50 | 33.80-125.13 | 5.76% |
| `multi_local` | 6,752 | 23.72 | 60.33 | 0.407 | 14-50 | 33.85-125.50 | 5.78% |
| `multi_distributed` | 6,818 | 23.55 | 59.87 | 0.408 | 14-50 | 33.84-125.29 | 5.82% |
| `reasoning` | 6,829 | 23.55 | 59.78 | 0.408 | 14-50 | 33.55-125.11 | 5.54% |
| `unanswerable` | 3,695 | 24.18 | 61.38 | 0.227 | 14-50 | 33.79-125.09 | 6.60% |
| **Total** | 37,783 | 23.62 | 60.00 | 2.267 | 14-50 | 33.55-125.50 | 5.82% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,322 | 17.74% | 9,284 | 24.57% |
| Mathematics | 1,235 | 16.58% | 8,823 | 23.35% |
| Computer Science | 1,229 | 16.50% | 9,119 | 24.14% |
| Biology | 716 | 9.61% | 1,457 | 3.86% |
| Medicine | 659 | 8.85% | 1,561 | 4.13% |
| Economics | 638 | 8.56% | 1,651 | 4.37% |
| Social Science | 636 | 8.54% | 1,640 | 4.34% |
| Engineering | 629 | 8.44% | 3,153 | 8.35% |
| Earth Science | 365 | 4.90% | 994 | 2.63% |
| Language and Literature | 12 | 0.16% | 43 | 0.11% |
| Other | 9 | 0.12% | 58 | 0.15% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,668 | 15.00% |
| Float | 2,423 | 6.41% |
| List | 12,928 | 34.22% |
| String | 13,069 | 34.59% |
| Unanswerable | 3,695 | 9.78% |

There are **34,088 answerable** and **3,695 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,695, 1 pages: 17,198, 2 pages: 11,408, 3 pages: 4,329, 4 pages: 1,145, 5 pages: 5, 6 pages: 2, 7 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 827 |
| 2 | 4,216 |
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
| released_prompt_window_v1 | 3,347 |
| document_tool_agent_v1 | 2,004 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 2,921 |
| Crossref subject-query sampling; provisional until generator topic vote | 77 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 7,445 | 99.933% | 37,743 |
| Spanish (`es`) | 2 | 0.027% | 14 |
| French (`fr`) | 1 | 0.013% | 2 |
| Russian (`ru`) | 1 | 0.013% | 12 |
| Chinese (`zh`) | 1 | 0.013% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 75.49% | 1.745 |
| `gpt-5.6-sol` | 5,043 | 9,259 | 24.51% | 0.522 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 5,043 | 9,259 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
