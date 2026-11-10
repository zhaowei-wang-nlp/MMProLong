# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 38,691 QA examples, 7,947 source PDFs, 179,704 unique page images, and 2,314,394,982 estimated training tokens (approximately 2.314B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/c6a7a67b297ee03f2ec6dccee61d0159f85288e6); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 7,947 |
| Document family | Public research papers |
| Unique rendered page images | 179,704 |
| Document pages: mean / median | 22.61 / 20 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-39 |
| Admitted QA examples | 38,691 |
| Estimated training tokens | 2,314,394,982 (2.314B) |
| Per-QA tokens: mean / median | 59.817K / 53.283K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,624 (6.78%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,204 (5.70%) |
| Page references across all QA contexts | 911,047 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 3,541 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 14,017 | 23.41 | 59.45 | 0.833 | 14-50 | 33.80-125.13 | 5.64% |
| `multi_local` | 6,914 | 23.67 | 60.19 | 0.416 | 14-50 | 33.85-125.50 | 5.66% |
| `multi_distributed` | 6,983 | 23.48 | 59.68 | 0.417 | 14-50 | 33.84-125.29 | 5.70% |
| `reasoning` | 6,989 | 23.48 | 59.61 | 0.417 | 14-50 | 33.55-125.11 | 5.44% |
| `unanswerable` | 3,788 | 24.07 | 61.12 | 0.232 | 14-50 | 33.79-125.09 | 6.47% |
| **Total** | 38,691 | 23.55 | 59.82 | 2.314 | 14-50 | 33.55-125.50 | 5.70% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,323 | 16.65% | 9,286 | 24.00% |
| Computer Science | 1,250 | 15.73% | 9,159 | 23.67% |
| Mathematics | 1,236 | 15.55% | 8,825 | 22.81% |
| Biology | 837 | 10.53% | 1,668 | 4.31% |
| Medicine | 773 | 9.73% | 1,769 | 4.57% |
| Economics | 716 | 9.01% | 1,797 | 4.64% |
| Social Science | 706 | 8.88% | 1,770 | 4.57% |
| Engineering | 696 | 8.76% | 3,278 | 8.47% |
| Earth Science | 388 | 4.88% | 1,036 | 2.68% |
| Language and Literature | 13 | 0.16% | 45 | 0.12% |
| Other | 9 | 0.11% | 58 | 0.15% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,789 | 14.96% |
| Float | 2,566 | 6.63% |
| List | 13,302 | 34.38% |
| String | 13,246 | 34.24% |
| Unanswerable | 3,788 | 9.79% |

There are **34,903 answerable** and **3,788 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,788, 1 pages: 17,597, 2 pages: 11,714, 3 pages: 4,401, 4 pages: 1,181, 5 pages: 6, 6 pages: 3, 7 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 913 |
| 2 | 4,627 |
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
| released_prompt_window_v1 | 3,915 |
| document_tool_agent_v1 | 2,344 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 3,408 |
| Crossref subject-query sampling; provisional until generator topic vote | 87 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 7,942 | 99.937% | 38,651 |
| Spanish (`es`) | 2 | 0.025% | 14 |
| French (`fr`) | 1 | 0.013% | 2 |
| Russian (`ru`) | 1 | 0.013% | 12 |
| Chinese (`zh`) | 1 | 0.013% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 73.72% | 1.745 |
| `gpt-5.6-sol` | 5,540 | 10,167 | 26.28% | 0.570 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 5,540 | 10,167 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
