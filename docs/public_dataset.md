# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-09): 34,212 QA examples, 5,458 source PDFs, 128,188 unique page images, and 2,079,092,954 estimated training tokens (approximately 2.079B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/d189e0d6766997ec76dc834f9e19aac2cef988b3); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 5,458 |
| Document family | Public research papers |
| Unique rendered page images | 128,188 |
| Document pages: mean / median | 23.49 / 21 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-41 |
| Admitted QA examples | 34,212 |
| Estimated training tokens | 2,079,092,954 (2.079B) |
| Per-QA tokens: mean / median | 60.771K / 53.469K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,602 (7.61%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,186 (6.39%) |
| Page references across all QA contexts | 818,295 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 17 |
| plos | 1,055 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 12,388 | 23.80 | 60.44 | 0.749 | 14-50 | 33.80-125.13 | 6.34% |
| `multi_local` | 6,134 | 23.93 | 60.88 | 0.373 | 14-50 | 33.85-125.50 | 6.33% |
| `multi_distributed` | 6,172 | 23.87 | 60.68 | 0.374 | 14-50 | 33.84-125.29 | 6.40% |
| `reasoning` | 6,175 | 23.88 | 60.64 | 0.374 | 14-50 | 33.55-125.11 | 6.09% |
| `unanswerable` | 3,343 | 24.51 | 62.23 | 0.208 | 14-50 | 33.79-125.09 | 7.24% |
| **Total** | 34,212 | 23.92 | 60.77 | 2.079 | 14-50 | 33.55-125.50 | 6.39% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,321 | 24.20% | 9,282 | 27.13% |
| Mathematics | 1,223 | 22.41% | 8,802 | 25.73% |
| Computer Science | 1,174 | 21.51% | 9,019 | 26.36% |
| Engineering | 368 | 6.74% | 2,673 | 7.81% |
| Biology | 301 | 5.51% | 723 | 2.11% |
| Medicine | 294 | 5.39% | 920 | 2.69% |
| Economics | 289 | 5.29% | 1,020 | 2.98% |
| Social Science | 280 | 5.13% | 1,003 | 2.93% |
| Earth Science | 193 | 3.54% | 680 | 1.99% |
| Other | 8 | 0.15% | 56 | 0.16% |
| Language and Literature | 7 | 0.13% | 34 | 0.10% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,175 | 15.13% |
| Float | 1,807 | 5.28% |
| List | 11,500 | 33.61% |
| String | 12,387 | 36.21% |
| Unanswerable | 3,343 | 9.77% |

There are **30,869 answerable** and **3,343 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,343, 1 pages: 15,589, 2 pages: 10,220, 3 pages: 4,034, 4 pages: 1,022, 5 pages: 2, 6 pages: 1, 7 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 414 |
| 2 | 2,637 |
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
| released_prompt_window_v1 | 1,103 |
| document_tool_agent_v1 | 677 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 982 |
| Crossref subject-query sampling; provisional until generator topic vote | 24 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 5,453 | 99.908% | 34,172 |
| Spanish (`es`) | 2 | 0.037% | 14 |
| French (`fr`) | 1 | 0.018% | 2 |
| Russian (`ru`) | 1 | 0.018% | 12 |
| Chinese (`zh`) | 1 | 0.018% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 83.37% | 1.745 |
| `gpt-5.6-sol` | 3,051 | 5,688 | 16.63% | 0.334 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 3,051 | 5,688 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
