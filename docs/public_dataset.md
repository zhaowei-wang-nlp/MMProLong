# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 42,007 QA examples, 9,805 source PDFs, 217,733 unique page images, and 2,486,577,693 estimated training tokens (approximately 2.487B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/af99961951f400a761ce8368ace57957e9c9648a); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 9,805 |
| Document family | Public research papers |
| Unique rendered page images | 217,733 |
| Document pages: mean / median | 22.21 / 20 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-38 |
| Admitted QA examples | 42,007 |
| Estimated training tokens | 2,486,577,693 (2.487B) |
| Per-QA tokens: mean / median | 59.194K / 53.261K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,650 (6.31%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,226 (5.30%) |
| Page references across all QA contexts | 978,917 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 5,399 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 15,242 | 23.15 | 58.78 | 0.896 | 14-50 | 33.80-125.13 | 5.23% |
| `multi_local` | 7,464 | 23.50 | 59.77 | 0.446 | 14-50 | 33.85-125.50 | 5.27% |
| `multi_distributed` | 7,590 | 23.21 | 59.00 | 0.448 | 14-50 | 33.84-125.29 | 5.30% |
| `reasoning` | 7,597 | 23.22 | 58.95 | 0.448 | 14-50 | 33.55-125.11 | 5.05% |
| `unanswerable` | 4,114 | 23.83 | 60.50 | 0.249 | 14-50 | 33.79-125.09 | 6.08% |
| **Total** | 42,007 | 23.30 | 59.19 | 2.487 | 14-50 | 33.55-125.50 | 5.30% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Biology | 1,369 | 13.96% | 2,590 | 6.17% |
| Physics | 1,331 | 13.57% | 9,302 | 22.14% |
| Computer Science | 1,309 | 13.35% | 9,258 | 22.04% |
| Mathematics | 1,247 | 12.72% | 8,846 | 21.06% |
| Medicine | 1,203 | 12.27% | 2,553 | 6.08% |
| Social Science | 975 | 9.94% | 2,249 | 5.35% |
| Economics | 959 | 9.78% | 2,238 | 5.33% |
| Engineering | 948 | 9.67% | 3,735 | 8.89% |
| Earth Science | 435 | 4.44% | 1,120 | 2.67% |
| Language and Literature | 20 | 0.20% | 58 | 0.14% |
| Other | 9 | 0.09% | 58 | 0.14% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 6,323 | 15.05% |
| Float | 3,053 | 7.27% |
| List | 14,611 | 34.78% |
| String | 13,906 | 33.10% |
| Unanswerable | 4,114 | 9.79% |

There are **37,893 answerable** and **4,114 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 4,114, 1 pages: 19,115, 2 pages: 12,785, 3 pages: 4,676, 4 pages: 1,298, 5 pages: 10, 6 pages: 6, 7 pages: 1, 8 pages: 1, 9 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 1,313 |
| 2 | 6,085 |
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
| released_prompt_window_v1 | 5,992 |
| document_tool_agent_v1 | 3,583 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 5,234 |
| Crossref subject-query sampling; provisional until generator topic vote | 119 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 9,800 | 99.949% | 41,967 |
| Spanish (`es`) | 2 | 0.020% | 14 |
| French (`fr`) | 1 | 0.010% | 2 |
| Russian (`ru`) | 1 | 0.010% | 12 |
| Chinese (`zh`) | 1 | 0.010% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 67.90% | 1.745 |
| `gpt-5.6-sol` | 7,398 | 13,483 | 32.10% | 0.742 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 7,398 | 13,483 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
