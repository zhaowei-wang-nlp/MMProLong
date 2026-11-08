# MMProLong public dataset: provenance, labels, and statistics

[Hugging Face dataset](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public) | [Full dataset card](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/README.md) | [MMProLong paper](https://arxiv.org/abs/2605.13831) | [Project README](../README.md)

**This is a separately constructed public corpus, not the original training data used in the MMProLong paper. Due to ByteDance's internal data governance and management requirements, the original paper corpus cannot be open-sourced.** The public corpus is constructed from public arXiv documents and does not establish reproduction of the paper's reported results.

The current production pipeline uses **GPT-5.6-sol**. The snapshot also contains historical **GPT-5.5** examples; the exact breakdown and per-document sampling history are reported below. Cite the [MMProLong paper](../README.md#citation) when using this public release.

## Scope and conventions

This page describes the admitted public snapshot identified below. It is a separately constructed arXiv corpus, with a GPT-based full-document generation/review pipeline and five QA types. The original paper used Seed 2.0 and coherent 8-15-page segments for its VQA synthesis. Its source pool and experimental results are separate from this release.

The manuscript defines binary prefixes (K=1024, B=2^30). Public tables use decimal K=1,000 and B=1,000,000,000; the >=100Ki statistic uses 102,400 to match the paper threshold. Exact raw counts and per-document labels are published with the dataset.

<!-- PUBLIC_CORPUS_STATS_START -->
**Public snapshot (2026-11-09): 32,064 QA examples, 4,263 source PDFs, 102,948 unique page images, and 1,963,498,927 estimated training tokens (approximately 1.963B).**

[This published snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/5a2fd9a7bdadbfece7c93e7b18a4ed20465a7f0a); [latest data](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public).

### Corpus scale

| Statistic | Public snapshot value |
| --- | --- |
| Admitted unique PDFs | 4,263 |
| Document family | arXiv research papers |
| Unique rendered page images | 102,948 |
| Document pages: mean / median | 24.15 / 22 |
| Document pages: range / 5th-95th percentile | 14-50 / 14-42 |
| Admitted QA examples | 32,064 |
| Estimated training tokens | 1,963,498,927 (1.963B) |
| Per-QA tokens: mean / median | 61.237K / 54.789K |
| Observed token range | 33,547-125,503 |
| At least 100,000 tokens | 2,572 (8.02%) |
| At least 100Ki = 102,400 tokens (paper threshold) | 2,158 (6.73%) |
| Page references across all QA contexts | 772,738 |

Tokens are the stored Qwen2.5-VL serialized-sample estimate, including full page-image context and QA/prompt text. A PDF used by several questions contributes its context repeatedly to the training-token total. This is not a count of unique-text tokens or billed API tokens. Page images are physically stored once per document.

![Public-corpus overview](assets/public_dataset/public_corpus_overview.png)

### Task-level statistics

| Task | QA | Avg. pages | Avg. K tokens | B tokens | Pages | K-token range | >=100Ki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 11,602 | 23.99 | 60.93 | 0.707 | 14-50 | 33.80-125.13 | 6.67% |
| `multi_local` | 5,772 | 24.07 | 61.24 | 0.353 | 14-50 | 33.85-125.50 | 6.67% |
| `multi_distributed` | 5,779 | 24.05 | 61.15 | 0.353 | 14-50 | 33.84-125.29 | 6.73% |
| `reasoning` | 5,780 | 24.07 | 61.13 | 0.353 | 14-50 | 33.55-125.11 | 6.45% |
| `unanswerable` | 3,131 | 24.70 | 62.72 | 0.196 | 14-50 | 33.79-125.09 | 7.57% |
| **Total** | 32,064 | 24.10 | 61.24 | 1.963 | 14-50 | 33.55-125.50 | 6.73% |

`K = 1,000`, `B = 1,000,000,000`; `100Ki = 102,400` tokens. Average pages in this table are **QA-weighted**, whereas the corpus-scale document average counts each PDF once. The two multi-page rows may be combined for comparison with the paper's broader extraction category. Unanswerable QA is an additional public-data task. Exact values, quantiles, and the combined task grouping are in [`metadata/statistics.json`](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/blob/main/metadata/statistics.json).

![Token-length distributions by task](assets/public_dataset/token_length_by_task.png)

### Primary-domain distribution

| Primary domain | Documents | Document share | QA | QA share |
| --- | --- | --- | --- | --- |
| Physics | 1,300 | 30.49% | 9,240 | 28.82% |
| Mathematics | 1,156 | 27.12% | 8,671 | 27.04% |
| Computer Science | 1,147 | 26.91% | 8,972 | 27.98% |
| Engineering | 343 | 8.05% | 2,626 | 8.19% |
| Social Science | 85 | 1.99% | 653 | 2.04% |
| Economics | 80 | 1.88% | 643 | 2.01% |
| Medicine | 60 | 1.41% | 501 | 1.56% |
| Earth Science | 51 | 1.20% | 427 | 1.33% |
| Biology | 28 | 0.66% | 245 | 0.76% |
| Other | 8 | 0.19% | 56 | 0.17% |
| Language and Literature | 5 | 0.12% | 30 | 0.09% |

Document and QA shares differ because historical phases generated different numbers of questions per PDF. Domain labels describe the source PDF, not a separate topic inferred for each question.

### Answer types and per-document sampling

| Answer format | QA | Share |
| --- | --- | --- |
| Integer | 4,824 | 15.04% |
| Float | 1,508 | 4.70% |
| List | 10,710 | 33.40% |
| String | 11,891 | 37.09% |
| Unanswerable | 3,131 | 9.76% |

There are **28,933 answerable** and **3,131 unanswerable** QA examples. The observed necessary-evidence page counts are: 0 pages: 3,131, 1 pages: 14,620, 2 pages: 9,508, 3 pages: 3,850, 4 pages: 955.

<details>
<summary>Observed QA count per source document</summary>

| QA per document | Documents |
| --- | --- |
| 1 | 172 |
| 2 | 1,684 |
| 6 | 1 |
| 8 | 1 |
| 9 | 7 |
| 10 | 51 |
| 11 | 259 |
| 12 | 2,084 |
| 20 | 4 |

The 20-QA documents belong to the initial pilot; the two-QA limit applies to the current GPT-5.6 phase.

</details>

### Domain-label provenance

| Recorded method | Documents |
| --- | --- |
| majority of full-context generator domain labels | 4,148 |
| arXiv primary category mapping | 106 |
| manual primary-topic classification for validated pilot batches | 9 |

## Document language

| Estimated document language | Documents | Document share | Associated QA |
| --- | --- | --- | --- |
| English (`en`) | 4,258 | 99.883% | 32,024 |
| Spanish (`es`) | 2 | 0.047% | 14 |
| French (`fr`) | 1 | 0.023% | 2 |
| Russian (`ru`) | 1 | 0.023% | 12 |
| Chinese (`zh`) | 1 | 0.023% | 12 |

Language labels are automatic estimates from sampled embedded PDF text; non-English/uncertain predictions receive a prose-filter recheck. They are not human-verified. Method, sampled pages, scores and recheck provenance are retained with each document.

## Generation provenance

| Recorded generation model | Documents | QA | QA share | B training tokens |
| --- | --- | --- | --- | --- |
| `gpt-5.5-2026-04-24` | 2,407 | 28,524 | 88.96% | 1.745 |
| `gpt-5.6-sol` | 1,856 | 3,540 | 11.04% | 0.219 |

| Phase | Documents | QA | Maximum QA per document |
| --- | --- | --- | --- |
| Initial pilot (GPT-5.5) | 4 | 80 | 20 |
| GPT-5.5 production | 2,403 | 28,444 | 12 |
| Current GPT-5.6 production | 1,856 | 3,540 | 2 |

The current snapshot is a **mixed-model historical release**, not an all-GPT-5.6 corpus. Use the `model` field when a model-specific subset is required.

![Evidence distribution](assets/public_dataset/evidence_distribution.png)

<!-- PUBLIC_CORPUS_STATS_END -->

## Download and reproduce

Follow the [dataset card's download instructions](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#download-and-use). Images are shared once per PDF and restored from checksummed archives. The reference-only training Parquet uses relative image paths; load image bytes on demand rather than duplicating all pages for every question.

The [public synthesis snapshot](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public/tree/main/code) is hosted with the data. This repository provides the reproducible [statistics generator](../scripts/profile_public_dataset.py), [initial language annotator](../scripts/annotate_public_document_languages.py), and [language recheck](../scripts/recheck_public_document_languages.py). The statistics script only needs the small QA/metadata files and optional published language labels; it does not need the restored PDF/image corpus. Language recomputation streams verified source archives in memory and fetches selected PDF byte ranges for rechecks.

Source documents retain their article-level licenses and exceptions. The code license does not assign a blanket license to source PDFs or synthetic QA. See the [dataset card's rights and quality notes](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public#quality-checks-and-limitations).
