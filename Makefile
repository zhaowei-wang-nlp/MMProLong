.PHONY: build quality style test-release test

# Lint the release-owned surface; framework-wide checks need the full GPU environment.
check_dirs := tasks/omni/train_qwen_vl.py tasks/data/vlm_data_process.py data_synthesis_doc_vqa scripts/merge_dcp_to_hf.py tests/release veomni/utils/multisource_utils.py

build:
	uv build

quality:
	ruff check $(check_dirs)
	ruff format --check $(check_dirs)

style:
	ruff check $(check_dirs) --fix
	ruff format $(check_dirs)

test-release:
	python -m unittest discover -s tests/release -v

# Requires VeOmni dependencies and suitable hardware; not the portable release check.
test:
	pytest tests/
