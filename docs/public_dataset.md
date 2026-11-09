# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-09): 32,447 QA examples, 4,463 source PDFs, 107,742 unique page images, and 1,986,799,667 estimated training tokens (approximately 1.987B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/0678faf1ed29a365c713ee89cc54d6135103fdb2); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 4,463 |
| Document family | Public research papers |
| Unique rendered page images | 107,742 |
| Document pages: mean / median | 24.14 / 22 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-42 |
| Admitted QA examples | 32,447 |
| Estimated training tokens | 1,986,799,667 (1.987B) |
| Per-QA tokens: mean / median | 61.232K / 54.796K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,585 (7.97%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,171 (6.69%) |
| Page references across all QA contexts | 781,914 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| plos | 77 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 11,742 | 23.98 | 60.91 | 0.715 | 14-50 | 33.80-125.13 | 6.63% |
| `multi_local` | 5,842 | 24.06 | 61.22 | 0.358 | 14-50 | 33.85-125.50 | 6.59% |
| `multi_distributed` | 5,848 | 24.05 | 61.16 | 0.358 | 14-50 | 33.84-125.29 | 6.70% |
| `reasoning` | 5,850 | 24.07 | 61.12 | 0.358 | 14-50 | 33.55-125.11 | 6.41% |
| `unanswerable` | 3,165 | 24.72 | 62.77 | 0.199 | 14-50 | 33.79-125.09 | 7.58% |
| **Total** | 32,447 | 24.10 | 61.23 | 1.987 | 14-50 | 33.55-125.50 | 6.69% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,321 | 29.60% | 9,282 | 28.61% |
| Mathematics | 1,221 | 27.36% | 8,799 | 27.12% |
| Computer Science | 1,164 | 26.08% | 9,001 | 27.74% |
| Engineering | 350 | 7.84% | 2,640 | 8.14% |
| Social Science | 96 | 2.15% | 673 | 2.07% |
| Economics | 83 | 1.86% | 649 | 2.00% |
| Biology | 79 | 1.77% | 341 | 1.05% |
| Medicine | 74 | 1.66% | 528 | 1.63% |
| Earth Science | 61 | 1.37% | 446 | 1.37% |
| Other | 8 | 0.18% | 56 | 0.17% |
| Language and Literature | 6 | 0.13% | 32 | 0.10% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 4,896 | 15.09% |
| Float | 1,527 | 4.71% |
| List | 10,812 | 33.32% |
| String | 12,047 | 37.13% |
| Unanswerable | 3,165 | 9.75% |

There are **29,282 answerable** and **3,165 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,165, 1 pages: 14,799, 2 pages: 9,620, 3 pages: 3,897, 4 pages: 966.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 189 |
| 2 | 1,867 |
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
| document_tool_agent_v1 | 8 |
| released_prompt_window_v1 | 7 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| Crossref subject-query sampling; provisional until generator topic vote | 3 |
| majority of independent full-document verifier topic labels | 8 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 4,458 | 99.888% | 32,407 |
| Spanish (`es`) | 2 | 0.045% | 14 |
| French (`fr`) | 1 | 0.022% | 2 |
| Russian (`ru`) | 1 | 0.022% | 12 |
| Chinese (`zh`) | 1 | 0.022% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 87.91% | 1.745 |
| `gpt-5.6-sol` | 2,056 | 3,923 | 12.09% | 0.242 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 2,056 | 3,923 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
