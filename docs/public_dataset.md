# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 39,739 QA examples, 8,538 source PDFs, 191,774 unique page images, and 2,368,519,161 estimated training tokens (approximately 2.369B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/18ed85259ec8c1d27de0298e0e1f19c595549c0e); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 8,538 |
| Document family | Public research papers |
| Unique rendered page images | 191,774 |
| Document pages: mean / median | 22.46 / 20 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-38 |
| Admitted QA examples | 39,739 |
| Estimated training tokens | 2,368,519,161 (2.369B) |
| Per-QA tokens: mean / median | 59.602K / 53.273K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,633 (6.63%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,212 (5.57%) |
| Page references across all QA contexts | 932,381 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 4,132 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 14,409 | 23.32 | 59.21 | 0.853 | 14-50 | 33.80-125.13 | 5.50% |
| `multi_local` | 7,083 | 23.60 | 60.03 | 0.425 | 14-50 | 33.85-125.50 | 5.53% |
| `multi_distributed` | 7,174 | 23.40 | 59.47 | 0.427 | 14-50 | 33.84-125.29 | 5.58% |
| `reasoning` | 7,181 | 23.39 | 59.39 | 0.427 | 14-50 | 33.55-125.11 | 5.32% |
| `unanswerable` | 3,892 | 23.98 | 60.88 | 0.237 | 14-50 | 33.79-125.09 | 6.32% |
| **Total** | 39,739 | 23.46 | 59.60 | 2.369 | 14-50 | 33.55-125.50 | 5.57% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,325 | 15.52% | 9,290 | 23.38% |
| Computer Science | 1,269 | 14.86% | 9,189 | 23.12% |
| Mathematics | 1,239 | 14.51% | 8,830 | 22.22% |
| Biology | 983 | 11.51% | 1,917 | 4.82% |
| Medicine | 922 | 10.80% | 2,038 | 5.13% |
| Social Science | 807 | 9.45% | 1,951 | 4.91% |
| Economics | 787 | 9.22% | 1,927 | 4.85% |
| Engineering | 771 | 9.03% | 3,413 | 8.59% |
| Earth Science | 410 | 4.80% | 1,075 | 2.71% |
| Language and Literature | 16 | 0.19% | 51 | 0.13% |
| Other | 9 | 0.11% | 58 | 0.15% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,962 | 15.00% |
| Float | 2,710 | 6.82% |
| List | 13,722 | 34.53% |
| String | 13,453 | 33.85% |
| Unanswerable | 3,892 | 9.79% |

There are **35,847 answerable** and **3,892 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,892, 1 pages: 18,080, 2 pages: 12,043, 3 pages: 4,492, 4 pages: 1,220, 5 pages: 7, 6 pages: 3, 7 pages: 1, 8 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 1,047 |
| 2 | 5,084 |
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
| released_prompt_window_v1 | 4,569 |
| document_tool_agent_v1 | 2,738 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 3,994 |
| Crossref subject-query sampling; provisional until generator topic vote | 92 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 8,533 | 99.941% | 39,699 |
| Spanish (`es`) | 2 | 0.023% | 14 |
| French (`fr`) | 1 | 0.012% | 2 |
| Russian (`ru`) | 1 | 0.012% | 12 |
| Chinese (`zh`) | 1 | 0.012% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 71.78% | 1.745 |
| `gpt-5.6-sol` | 6,131 | 11,215 | 28.22% | 0.624 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 6,131 | 11,215 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
