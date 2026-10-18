# Contributing to MMProLong

This repository is a research fork of VeOmni. Open MMProLong [issues](https://github.com/zhaowei-wang-nlp/MMProLong/issues) and [pull requests](https://github.com/zhaowei-wang-nlp/MMProLong/pulls) in this fork; use the [upstream project](https://github.com/ByteDance-Seed/VeOmni) for independently reproduced framework issues.

Follow [README.md](README.md) for the Python 3.11 GPU environment. For portable release checks without GPUs:

```bash
python -m pip install pyyaml ruff==0.13.1
make test-release
make quality
```

The release checks cover launcher behavior and configuration integrity. The full inherited `tests/` suite additionally requires the appropriate VeOmni dependencies, model assets, and GPU/NPU hardware; run relevant framework tests when changing those components.

Keep training configurations explicit, use placeholder data paths, and document changes to experiment settings in [docs/reproduction_notes.md](docs/reproduction_notes.md). Do not commit credentials, local environment files, logs, data, or checkpoints. Preserve upstream copyright and license notices.
