# Long-Document VQA Data Synthesis

This folder contains the public-facing data synthesis pipeline used to build long-document VQA training examples for MMProLong.

Important: these scripts are **not an out-of-the-box runnable pipeline**. The document pool used in the paper is internal and cannot be released. The original internal preprocessing steps for filtering that private document pool, compacting internal parquet shards, and downloading PDF pages / OCR blocks from internal storage have been removed. For open-source use, this folder should be treated as a reusable reference implementation that starts from user-prepared document metadata, rendered page images, OCR block files, and few-shot exemplars.

A replacement pool made from publicly available PDFs is planned; it is not included in this release.

## What This Pipeline Does

Given a set of long documents represented as page images and OCR/layout metadata, the pipeline:

1. Renders single-page PDF files into page images: 1_convert_pdf_page_to_image.py
2. Prepares few-shot exemplars for QA generation: 2_filter_long_vqa_exemplar.py
3. Calls an OpenAI-compatible multimodal API to synthesize document-grounded QA pairs: 3_prompt_API_for_long_vqa_data.py
4. Builds VeOmni/LLaVA-style parquet files for long-context continued pre-training: 4_postprocess_VeOmni_format.py

The final examples contain a full-document visual context, a question, an answer, evidence metadata, token counts, and image bytes.

## Installation

After installing the training environment in the root README, install the synthesis dependencies:

```bash
uv pip install -r data_synthesis_doc_vqa/requirements.txt
```

## Expected Inputs

Because the internal document pool is not released, users need to prepare the following inputs themselves before running these scripts.

### 1. Metadata Parquet

The synthesis scripts expect a directory of parquet files. Each row should describe one document and include at least:

```text
source      string   Dataset/source name.
id          string   Document id within the source.
page_count  int      Number of pages in the document.
```

The scripts use `source` and `id` to construct deterministic page-image and OCR paths. For the current reference implementation, use a metadata directory such as `/path/to/min32page_max50page/parquet/` with numerically suffixed shard names such as `part-0.parquet`. The QA generation script reads the parent directory name to label page ranges, and generation/postprocessing parse shard numbers from filenames. Prepare rows within that page range; the folder name alone does not filter the input documents.

### 2. Page Images

Each document page should be available as an image, usually PNG. The default path convention is:

```text
{image_pool_path}/{source}/{first_char_of_id}/{source}__{id}_page{page_id}.png
```

For example:

```text
/path/to/workspace/pdf_data/pdf_pool_img_144dpi/my_source/a/my_source__abc123_page0.png
```

If your images are organized differently, update the path construction in `3_prompt_API_for_long_vqa_data.py` and `4_postprocess_VeOmni_format.py`.

### 3. OCR / Layout Blocks

Each document should have an OCR JSON file:

```text
{ocr_pool_path}/{source}/{id}.json
```

The QA generation script expects this file to be a list of page-level records. Each page record should contain:

```text
page_id      int
page_blocks  string  JSON-encoded list of OCR/layout blocks
```

Each block should include a `label` field. The script uses labels `title` and `sec` to identify section boundaries and sample semantically coherent 8-15 page spans.

### 4. Few-Shot Exemplar JSONL

Few-shot exemplars are used in the generation prompt. Each line should be a JSON object with fields like:

```text
question
answer
answer_format
detailed_evidences
evidence_pages
evidence_sources
```

`2_filter_long_vqa_exemplar.py` can filter a LongDocURL-style exemplar file into task-specific exemplar files.

## Files

### `1_convert_pdf_page_to_image.py`

Utility for rendering PDF files into PNG images.

Use this only if you already have PDF files. If you already have rendered page images, you can skip this step.

```bash
python data_synthesis_doc_vqa/1_convert_pdf_page_to_image.py \
  --input_dir /path/to/min32page_max50page/parquet \
  --pdf_pool /path/to/pdf_page_pool \
  --image_dir /path/to/pdf_page_image_pool \
  --dpi 144 \
  --num_proc 32
```

### `2_filter_long_vqa_exemplar.py`

Filters an existing exemplar JSONL file by question type and page scope.

This script currently uses top-level variables:

```python
current_question_type = ["calculate", "compare", "count"]
current_question_name = "math"
page_flag = "all_page"
input_path = "..."
output_path = "..."
```

Edit these values before running:

```bash
python data_synthesis_doc_vqa/2_filter_long_vqa_exemplar.py
```

### `3_prompt_API_for_long_vqa_data.py`

Main QA synthesis script.

For each metadata row, it:

- loads OCR blocks,
- finds title/section pages,
- samples a coherent 8-15 page span,
- builds a multimodal few-shot prompt,
- encodes page images as base64,
- calls an OpenAI-compatible chat completion API,
- writes one JSON record per generated QA example.

Set your API key before running:

```bash
export VQA_API_BASE_URL=https://your-provider.example/v1
export VQA_API_MODEL=your-multimodal-model
export VQA_API_KEY=your_api_key
```

Example:

```bash
python data_synthesis_doc_vqa/3_prompt_API_for_long_vqa_data.py \
  --input_dir /path/to/min32page_max50page/parquet \
  --image_pool_path /path/to/pdf_data/pdf_pool_img_144dpi \
  --ocr_pool_path /path/to/pdf_data/pdf_pool/book_blocks \
  --output_dir /path/to/long_vqa_output \
  --output_file_subdir tmp \
  --question_type extract \
  --page_flag multi_page \
  --exemplar_num 2 \
  --api_batch_size 12 \
  --start_idx 0 \
  --end_idx 120
```

Supported task/page combinations are defined in `prompt_utils.py`:

```text
question_type=extract, page_flag=single_page
question_type=extract, page_flag=multi_page
question_type=math,    page_flag=all_page
```

The API endpoint, model, and key are read from `VQA_API_BASE_URL`, `VQA_API_MODEL`, and `VQA_API_KEY`. `ARK_API_KEY` is accepted as a legacy key alias. Configure a multimodal chat-completions endpoint; no private deployment identifier is embedded in the source. These environment variables are not loaded automatically from `.env.example`.

### `4_postprocess_VeOmni_format.py`

Converts generated QA JSON files into VeOmni/LLaVA-style parquet files.

It:

- parses the model output into evidence description and QA JSON,
- reconstructs the full-document visual context,
- optionally appends evidence reasoning as CoT,
- truncates distractor pages while preserving evidence pages,
- filters examples by token length and page count,
- writes parquet files containing conversations and image bytes.

Example:

```bash
python data_synthesis_doc_vqa/4_postprocess_VeOmni_format.py \
  --input_dir /path/to/long_vqa_output/tmp_extract_multi_page \
  --output_dir /path/to/veomni_training_data \
  --output_file_subdir veomni/extract_multi_page_no_cot_v1 \
  --question_type extract \
  --page_flag multi_page \
  --add_cot False \
  --min_K_length 32 \
  --max_K_length 124 \
  --min_page 32 \
  --max_page 49 \
  --max_parquet_cnt 120 \
  --processor_name Qwen/Qwen2.5-VL-7B-Instruct \
  --num_proc 32
```

The original data paths were named `min32max49`, so the example preserves an inclusive 32–49 page filter. The paper describes 32–50 pages; confirm the original corpus boundary before claiming exact reproduction. The default upper token filter is 124K, leaving headroom under the 128K training maximum. Both bounds are user-configurable. The script appends `min{min_page}max{max_page}-` and `-par{max_parquet_cnt}` to `output_file_subdir`; point each training YAML source to the actual resulting parquet directory.

### `prompt_utils.py`

Prompt templates for QA generation.

It defines:

- the shared QA generation prompt,
- exemplar formatting,
- extraction task instructions,
- math/reasoning task instructions,
- task-specific exemplar file paths.

Update exemplar file paths before running `3_prompt_API_for_long_vqa_data.py`.

### `api_parse_utils.py`

Parsing utilities for API outputs.

It extracts:

- evidence description,
- JSON QA fields,
- question,
- answer,
- answer format,
- evidence pages,
- evidence sources.

It also includes a fallback regex-based JSON extraction path for imperfect model outputs.

### `utils.py`

Shared helpers:

- `listdir()` supports both local paths and HDFS-style paths.

## Output Format

The final parquet files produced by `4_postprocess_VeOmni_format.py` include fields such as:

```text
id
source
global_id
conversations
images
source_name
qa_json
qa_evidence_description
token_count
page_count
qa_page_idx_list
```

`conversations` is serialized JSON in LLaVA-style format. `images` stores page image bytes.

## Recommended Public Workflow

For external users, the expected workflow is:

```bash
# Optional: render page PDFs into images
python data_synthesis_doc_vqa/1_convert_pdf_page_to_image.py ...

# Optional: prepare task-specific few-shot exemplars
python data_synthesis_doc_vqa/2_filter_long_vqa_exemplar.py

# Generate long-document QA examples
export VQA_API_BASE_URL=https://your-provider.example/v1
export VQA_API_MODEL=your-multimodal-model
export VQA_API_KEY=your_api_key
python data_synthesis_doc_vqa/3_prompt_API_for_long_vqa_data.py ...

# Convert generated QA into VeOmni training parquet
python data_synthesis_doc_vqa/4_postprocess_VeOmni_format.py ...
```

## Notes and Limitations

- This folder does not include the private document pool used in the paper, so the scripts are not expected to run successfully without user-prepared replacement data.
- Users must prepare their own metadata parquet, page images, OCR blocks, and API credentials.
- The default path values are placeholders and should be replaced with local paths. Check the filename/directory conventions above; these scripts retain those conventions from the reference pipeline.
- Render at 144 DPI and preserve page order. Generate the three task pools separately and point the main mixture YAML at their output directories.
- Remove evaluation-document overlap (the paper uses PDF SHA-256 hashes) before synthesis and training.
- The QA generation step can be expensive because it sends page images to a multimodal model API.
- The postprocessing step uses the Qwen2.5-VL processor to estimate multimodal token counts.
- For best results, make sure OCR section labels are reliable, since section sampling depends on `title` and `sec` labels.
