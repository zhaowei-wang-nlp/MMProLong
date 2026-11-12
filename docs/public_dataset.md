# MMProLong public dataset

[Load the dataset on Hugging Face](https://huggingface.co/datasets/ZhaoweiWang/MMProLong-Data-Public)

[Paper](https://arxiv.org/abs/2605.13831) · [GitHub](https://github.com/zhaowei-wang-nlp/MMProLong)

**This is a separately constructed public corpus, not the original data used in the MMProLong paper. The original corpus cannot be released under ByteDance's internal data governance and management requirements.** This public release does not establish reproduction of the paper's reported results.

**New production uses GPT-5.6 (`gpt-5.6-sol`).** Historical GPT-5.5 examples retain their original model labels. Please cite the MMProLong paper when using this dataset or its synthesis methodology.

## Dataset format

The release consists of this card and `data/train-*.parquet`. **Each row is one QA example and contains every page image of its source PDF, in order.** Images are embedded in the parquet as Hugging Face `Image` values; no separate PDF/image archive or restoration step is required.

The page images use a smaller lossless encoding where beneficial. Every conversion is decoded and checked for identical RGBA pixels and dimensions. All questions, answers, page indices, full-document coverage and stored token counts are preserved. QA from the same document share a parquet image dictionary to reduce physical duplication.

## Load the data

```python
from datasets import load_dataset

dataset = load_dataset(
    "ZhaoweiWang/MMProLong-Data-Public", split="train", streaming=True, batch_size=1
)
example = next(iter(dataset))
print(example["question"], example["answer"])
print(example["kind"], example["evidence_pages"])
pages = example["images"]  # ordered PIL images for the complete PDF
```

For image bytes instead of decoded images, cast `images` to `datasets.Sequence(datasets.Image(decode=False))`. `conversations` contains the original serialized training dialogue, including the document's image placeholders.

## Published statistics

Snapshot date: **2026-11-12**. These are measured counts of the published rows.

| Statistic | Value |
| --- | --- |
| QA examples | 75,442 |
| Source documents | 28,571 |
| Unique PDF pages | 599,114 |
| Estimated training tokens | 4,212,923,390 (4.213B) |
| Average tokens per QA | 55,843 |
| Median tokens per QA | 50,732 |
| Token range per QA | 33,547–125,503 |
| Average pages per document | 21.0 |
| PDF page range | 14–50 |
| Parquet shards | 580 |

Training tokens are the stored Qwen2.5-VL serialized-sample estimate, including page-image context and QA/prompt text. They are not billed API tokens or unique document-text tokens. A document used by several QA examples contributes its full context to each training example.

### Tasks

| Task | QA | Mean pages per QA | Mean tokens per QA |
| --- | --- | --- | --- |
| Single-page extraction | 27,437 | 21.8 | 55,306 |
| Local multi-page extraction | 13,234 | 22.5 | 57,197 |
| Distributed multi-page extraction | 13,658 | 21.9 | 55,533 |
| Reasoning | 13,616 | 22.0 | 55,709 |
| Unanswerable | 7,497 | 22.2 | 56,228 |

`single` is single-page extraction; `multi_local` requires nearby pages; `multi_distributed` requires separately necessary distant pages; `reasoning` requires a derived numerical answer; `unanswerable` requires missing information that cannot be recovered from the complete document. All evidence indices are zero-based PDF page indices. Unanswerable examples have empty `evidence_pages` and separate `related_context_pages`.

### Sources and domains

| Source | Documents |
| --- | --- |
| arxiv | 4,386 |
| elife | 20 |
| plos | 24,165 |

| Document domain | Documents | Document share | QA |
| --- | --- | --- | --- |
| Medicine | 7,388 | 25.86% | 13,447 |
| Biology | 6,455 | 22.59% | 11,488 |
| Social Science | 3,671 | 12.85% | 7,162 |
| Economics | 2,457 | 8.60% | 4,969 |
| Computer Science | 2,350 | 8.23% | 11,143 |
| Engineering | 2,201 | 7.70% | 6,000 |
| Mathematics | 1,528 | 5.35% | 9,376 |
| Physics | 1,398 | 4.89% | 9,423 |
| Earth Science | 1,009 | 3.53% | 2,163 |
| Language and Literature | 102 | 0.36% | 209 |
| Other | 12 | 0.04% | 62 |

Domain labels describe the source document and are automatic annotations, not human gold labels. `domain_tag_method` preserves their provenance. The source pool contains public research papers from multiple fields; it is not restricted to computer science. Sampling favors underrepresented domains, but the table reports the actual resulting distribution.

### Generation models

| Recorded generation model | QA | Estimated training tokens |
| --- | --- | --- |
| gpt-5.5-2026-04-24 | 28,524 | 1,744,611,453 |
| gpt-5.6-sol | 46,918 | 2,468,311,937 |

Use `model` to select a model-specific subset. The complete release is a mixed-model historical corpus.

## Columns

| Column | Meaning |
| --- | --- |
| `id`, `document_id` | Stable QA and source-document identifiers |
| `images` | Complete ordered page-image context, embedded bytes with logical filenames |
| `question`, `answer`, `answer_format` | QA target and answer format; structured answers are serialized as JSON text |
| `conversations` | Original serialized training dialogue |
| `kind`, `source_name`, `answerable` | Task category and answerability |
| `evidence_pages`, `related_context_pages` | Necessary evidence or related-context anchors, indexed from zero |
| `token_count`, `page_count` | Stored training-token estimate and full PDF page count |
| `source_domain`, `domain_tag_method`, `document_language` | Document annotations and domain-label provenance |
| `source_title`, `source_authors`, `source_url` | Source attribution and retrieval information |
| `license`, `license_url`, `context_sha256` | Original-document license and identity |
| `model`, `generation_method`, `verification_policy` | Recorded synthesis and review provenance |

## Construction and quality checks

Local tasks use the released 8–15-page sampler, original prompts and two LongDocURL few-shot examples. Distributed extraction, globally planned reasoning and unanswerable tasks use a GPT-5.6 document tool loop with overview, full-text search, page-text/image inspection and bounded arithmetic. Unanswerable agents receive every extracted text page and inspect relevant images; a zero-hit literal search is not proof of absence.

New hybrid examples require **two independent full-PDF reviews**, structural checks, executable arithmetic for numeric reasoning, necessary multi-page evidence and per-document semantic novelty checks. At most two QA are admitted per document in current production. Historical examples preserve their original model, sampling and review policy; some historical documents therefore have more QA.

Automated review is a filter, not a correctness guarantee. Domain/language annotations may contain errors. Benchmark decontamination and a GPU training-read evaluation have not been completed. Evaluate overlap with your own test sets before training.

## Source rights

The included source papers were admitted under CC BY 4.0 checks. Per-row title, authors, source URL and license fields preserve attribution. Cite and attribute the underlying documents as required by their licenses, as well as MMProLong. This release contains separately generated public data; it does not distribute the paper's original internal training corpus.

## Citation

```bibtex
@inproceedings{wang2026mmprolong,
  title={Training Long-Context Vision-Language Models Effectively with Generalization Beyond 128K Context},
  author={Wang, Zhaowei and Luo, Lishu and Duan, Haodong and Liu, Weiwei and Wu, Sijin and Luo, Ji and Yan, Shen and Peng, Shuai and Yuan, Sihang and Huang, Chaoyi and Lin, Yi and Song, Yangqiu},
  booktitle={Advances in Neural Information Processing Systems (NeurIPS 2026)},
  year={2026},
  url={https://arxiv.org/abs/2605.13831}
}
```
