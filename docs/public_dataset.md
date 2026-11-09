# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public research papers and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed public research-paper corpus, with a GPT-based hybrid generation pipeline, full-document review, and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-10): 35,116 QA examples, 5,958 source PDFs, 138,628 unique page images, and 2,126,922,250 estimated training tokens (approximately 2.127B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/95eb239c940a73c98132f70c6f63d94a16598ea4); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 5,958 |
| Document family | Public research papers |
| Unique rendered page images | 138,628 |
| Document pages: mean / median | 23.27 / 21 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-40 |
| Admitted QA examples | 35,116 |
| Estimated training tokens | 2,126,922,250 (2.127B) |
| Per-QA tokens: mean / median | 60.568K / 53.376K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,604 (7.42%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,188 (6.23%) |
| Page references across all QA contexts | 837,149 |

### Document sources

| Source | Unique documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 17 |
| plos | 1,555 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 12,716 | 23.72 | 60.23 | 0.766 | 14-50 | 33.80-125.13 | 6.18% |
| `multi_local` | 6,295 | 23.87 | 60.73 | 0.382 | 14-50 | 33.85-125.50 | 6.16% |
| `multi_distributed` | 6,336 | 23.77 | 60.44 | 0.383 | 14-50 | 33.84-125.29 | 6.23% |
| `reasoning` | 6,340 | 23.79 | 60.41 | 0.383 | 14-50 | 33.55-125.11 | 5.95% |
| `unanswerable` | 3,429 | 24.44 | 62.05 | 0.213 | 14-50 | 33.79-125.09 | 7.06% |
| **Total** | 35,116 | 23.84 | 60.57 | 2.127 | 14-50 | 33.55-125.50 | 6.23% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,321 | 22.17% | 9,282 | 26.43% |
| Mathematics | 1,225 | 20.56% | 8,805 | 25.07% |
| Computer Science | 1,185 | 19.89% | 9,040 | 25.74% |
| Biology | 415 | 6.97% | 930 | 2.65% |
| Medicine | 394 | 6.61% | 1,099 | 3.13% |
| Economics | 391 | 6.56% | 1,209 | 3.44% |
| Social Science | 380 | 6.38% | 1,182 | 3.37% |
| Engineering | 378 | 6.34% | 2,690 | 7.66% |
| Earth Science | 251 | 4.21% | 784 | 2.23% |
| Language and Literature | 10 | 0.17% | 39 | 0.11% |
| Other | 8 | 0.13% | 56 | 0.16% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 5,306 | 15.11% |
| Float | 1,964 | 5.59% |
| List | 11,869 | 33.80% |
| String | 12,548 | 35.73% |
| Unanswerable | 3,429 | 9.76% |

There are **31,687 answerable** and **3,429 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,429, 1 pages: 15,993, 2 pages: 10,524, 3 pages: 4,110, 4 pages: 1,055, 5 pages: 3, 6 pages: 1, 7 pages: 1.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 510 |
| 2 | 3,041 |
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
| released_prompt_window_v1 | 1,674 |
| document_tool_agent_v1 | 1,010 |

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,330 |
| arXiv primary category mapping | 113 |
| manual primary-topic classification for validated pilot batches | 9 |
| majority of independent full-document verifier topic labels | 1,473 |
| Crossref subject-query sampling; provisional until generator topic vote | 33 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 5,953 | 99.916% | 35,076 |
| Spanish (`es`) | 2 | 0.034% | 14 |
| French (`fr`) | 1 | 0.017% | 2 |
| Russian (`ru`) | 1 | 0.017% | 12 |
| Chinese (`zh`) | 1 | 0.017% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 81.23% | 1.745 |
| `gpt-5.6-sol` | 3,551 | 6,592 | 18.77% | 0.382 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 3,551 | 6,592 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
