# MMProLong: Training Long-Context Vision-Language Models Effectively with Generalization Beyond 128K Context

---

<p align="center">
    🎉 <strong>MMProLong is accepted to NeurIPS 2026!</strong>
</p>

<p align="center">
    <a href="https://github.com/zhaowei-wang-nlp/MMProLong">
        <img alt="Code on GitHub" src="https://img.shields.io/badge/Code-GitHub-black?logo=github">
    </a>
    <a href="https://arxiv.org/abs/2605.13831">
        <img alt="Paper on arXiv" src="https://img.shields.io/badge/Paper-arXiv-b31b1b?logo=arxiv">
    </a>
    <a href="https://huggingface.co/papers/2605.13831">
        <img alt="Hugging Face Papers" src="https://img.shields.io/badge/🤗-Hugging%20Face%20Papers-yellow">
    </a>
    <a href="https://github.com/ByteDance-Seed/VeOmni">
        <img alt="Fork of VeOmni" src="https://img.shields.io/badge/Fork%20of-VeOmni-blue">
    </a>
    <a href="LICENSE">
        <img alt="Code License: Apache 2.0" src="https://img.shields.io/badge/Code%20License-Apache%202.0-green">
    </a>
</p>

MMProLong studies how to train long-context vision-language models effectively through long-context continued pre-training (LongPT). Starting from Qwen2.5-VL-7B, it extends the training context from **32K to 128K** and generalizes to **256K and 512K** without additional training or inference-time adaptation. The paper reports a **7.11 percentage-point** improvement on long-document VQA, from 50.59 to 57.70, with transfer to webpage retrieval, vision-text compression, and long-video understanding.

**This repository is a research fork of [ByteDance-Seed/VeOmni](https://github.com/ByteDance-Seed/VeOmni).** VeOmni provides the training framework, distributed execution, model integrations, and checkpoint infrastructure. MMProLong adds long-document VQA synthesis, Qwen-VL training adaptations, and long-context data recipes. We retain the `veomni` package name and upstream copyright notices.

Please check out the [paper](https://arxiv.org/abs/2605.13831) for the study and results. This repository explains how to prepare data, run training, and export checkpoints.

## 📢 Latest Updates

- **[Oct 18, 2026]** 🚀 We release the [MMProLong code](https://github.com/zhaowei-wang-nlp/MMProLong), including **128K training recipes** for Qwen2.5-VL-7B and Qwen3-VL-8B, long-document VQA synthesis scripts, data-mixture ablations, and checkpoint export utilities.
- **Model checkpoints and training data are coming soon.** The original document pool is private; a replacement pool built from publicly available PDFs is planned.

## Quick Links

- [Setup](#setup)
- [Data](#data)
- [Running training](#running-training)
- [Running evaluation](#running-evaluation)
- [Tips](#tips)
- [Repository structure](#repository-structure)
- [Contacts](#contacts)
- [Citation](#citation)
- [Acknowledgment](#acknowledgment)
- [License](#license)

## Setup

The supplied GPU environment requires **Linux x86_64, Python 3.11, and NVIDIA GPUs** with compatible drivers. Dependencies are pinned to PyTorch 2.8.0 and CUDA 12.8. The recipes use FlashAttention 2; the GPU extra also installs FlashAttention 3.

Clone the repository and set up the environment:

```bash
git clone https://github.com/zhaowei-wang-nlp/MMProLong.git
cd MMProLong
python -m pip install 'uv==0.9.8'
uv sync --locked --extra gpu --group dev
source .venv/bin/activate
```

Use this checkout's `veomni` package to include the MMProLong changes. For general framework documentation, see [VeOmni](https://veomni.readthedocs.io/en/latest/).

## Data

Our final recipe uses **long-document VQA only**, with a pool-native distribution across 32K–128K multimodal tokens. It combines three supervision types:

- **Single-page extraction (40%)**: retrieve information from one page.
- **Multi-page extraction (40%)**: combine information across multiple pages.
- **Reasoning (20%)**: perform quantitative or logical reasoning over document evidence.

This gives an **8:2 extraction-to-reasoning ratio**, with no short data. The corresponding configuration is [long_doc_vqa_8_2.yaml](scripts/qwen_vl_mix_yaml/long_doc_vqa_8_2.yaml). Its weights control dataset sampling; the length distribution must be established when preparing the corpus.

### Prepare your training data

**The training corpus is not included yet.** To synthesize replacement data, follow [data_synthesis_doc_vqa/README.md](data_synthesis_doc_vqa/README.md). The reference pipeline requires your own documents, rendered page images, OCR metadata, few-shot exemplars, and API access.

Once your parquet shards are ready, copy the mixture configuration:

```bash
cp scripts/qwen_vl_mix_yaml/long_doc_vqa_8_2.yaml /shared/data/mmprolong-mixture.yaml
```

Replace all three `/path/to/data/...` source paths in the copied file with your actual parquet directories. Use the same absolute paths on every node. YAML environment-variable interpolation is not supported.

<details>
<summary>Training example format</summary>

Each example needs `conversations` (a LLaVA-style list or its JSON string) and `images` (page-image bytes in conversation order). Conversation turns use `from: human` / `from: gpt` and `value`; each `<image>` marker corresponds to one image. Multisource loading supplies the source name. Additional synthesis metadata may be retained. See the [data-synthesis guide](data_synthesis_doc_vqa/README.md#output-format) for the full output schema.

</details>

## Running training

The main training configuration is **[configs/mmprolong/qwen25_vl_7b_128k.yaml](configs/mmprolong/qwen25_vl_7b_128k.yaml)**. It contains the MMProLong defaults, including:

- **128K context**, global batch size **32**, and micro batch size **1**.
- A nominal **5,000,000,000-token** budget, preserving the original launch script.
- AdamW, peak language-model LR **1e-5**, **10% warmup**, and cosine decay to **1e-6**.
- FSDP2 with `data_parallel_shard_size=8`, **Ulysses size 2**, and gradient checkpointing.

The default parallel and batch settings support **16, 32, or 64 GPUs**. These counts describe the required topology; sufficient GPU memory is also needed. The paper reports training on 64 H20 GPUs. An 8-GPU run requires an explicit shard-size override and has not been validated in this release.

Download `Qwen/Qwen2.5-VL-7B-Instruct`, or allow Hugging Face to resolve it. For local weights, override both the model and tokenizer paths. Run from the repository root:

```bash
bash train.sh tasks/omni/train_qwen_vl.py \
  configs/mmprolong/qwen25_vl_7b_128k.yaml \
  --model.model_path /shared/models/Qwen2.5-VL-7B-Instruct \
  --model.tokenizer_path /shared/models/Qwen2.5-VL-7B-Instruct \
  --data.train_path /shared/data/mmprolong-mixture.yaml \
  --train.output_dir /shared/outputs/mmprolong
```

The launcher accepts standard `torchrun` environment variables and command-line overrides. For **8 nodes with 8 GPUs each**, run the following on every node, setting `NODE_RANK` from 0 to 7:

```bash
export NNODES=8 NPROC_PER_NODE=8
export NODE_RANK=0                    # Change on each node.
export MASTER_ADDR=rank-0-hostname MASTER_PORT=29500
bash scripts/qwen_vl_job/run_qwen25_vl_7b_vqa.sh \
  --data.train_path /shared/data/mmprolong-mixture.yaml \
  --train.output_dir /shared/outputs/mmprolong
```

Use shared data and output paths across nodes. W&B is opt-in via `--train.use_wandb true --train.wandb_name <run-name>`.

**Reproduction note:** the defaults preserve the original scripts rather than silently changing their settings to match the paper. Known differences and validation limits are recorded in [docs/reproduction_notes.md](docs/reproduction_notes.md). The included 128K model JSON was reconstructed from the public base config and the paper; equivalence to the original run assets still needs verification. See [Tips](#tips) for details.

### Qwen3-VL-8B

To run the backbone transfer experiment, use [qwen3_vl_8b_128k.yaml](configs/mmprolong/qwen3_vl_8b_128k.yaml), or its launch wrapper:

```bash
bash scripts/qwen_vl_job/run_qwen3_vl_8b_vqa.sh \
  --data.train_path /shared/data/mmprolong-mixture.yaml \
  --train.output_dir /shared/outputs/mmprolong-qwen3
```

This recipe uses Qwen3-VL's own pretrained model configuration and chat template.

### Export checkpoints

Training saves effective arguments to `veomni_cli.yaml` and the model configuration and processor to `model_assets/` inside the output directory. Export a distributed checkpoint with its **saved model assets** to retain the trained RoPE configuration:

```bash
bash scripts/qwen_vl_job/merge_script.sh \
  /shared/outputs/mmprolong/checkpoints/global_step_1193 \
  /shared/outputs/mmprolong/model_assets \
  /shared/outputs/mmprolong-hf
```

## Running evaluation

For **MMLongBench-Doc, LongDocURL, SlideVQA, and webpage MM-NIAH**, follow the official [MMLongBench](https://github.com/EdinburghNLP/MMLongBench) evaluation code and protocols.

For **VTCBench, Video-MME, MLVU, LongVideoBench, and short-context benchmarks**, use [VLMEvalKit](https://github.com/open-compass/VLMEvalKit) with the paper's settings.

The 256K/512K document experiments extend the benchmarks by padding negative documents on alternating sides, following MMLongBench. Those extended benchmark artifacts and experiment-specific evaluation wrappers are not included here. Reproducing the reported results requires matching benchmark versions, image/token budgets, prompts, and LLM-judge settings. The longer-context results use the 128K-trained model without additional adaptation.

## Tips

<details>
<summary>1. Model configuration and RoPE</summary>

The included [128K Qwen2.5-VL-7B configuration](configs/model_configs/qwen/mmprolong_qwen25_vl_7b_128k.json) sets `rope_theta=4000000`, `max_position_embeddings=131072`, and `use_cache=false`. It preserves Qwen's mRoPE sections without adding YaRN or dynamic inference scaling.

The original launcher referenced an unavailable `config_128K.json`. This replacement was reconstructed from the public base config and the paper, and should be checked against the original run's `model_assets/config.json` before claiming exact reproduction. It is specific to Qwen2.5-VL-7B; Qwen3-VL uses its own config.

The generic `configs/multimodal/qwen25_vl/qwen25_vl.yaml` is an inherited 4K example. Use `configs/mmprolong/qwen25_vl_7b_128k.yaml` for MMProLong training.

</details>

<details>
<summary>2. Token budget and optimizer settings</summary>

The released scripts use 5,000,000,000 tokens, one epoch, and 32 × 131,072 nominal tokens per update. With the default zero packing margin and batch warmup, this gives 1,193 optimizer steps. Actual consumed tokens depend on packing. The paper's definition of 5B differs; see the [reproduction notes](docs/reproduction_notes.md).

AdamW uses weight decay 0.1 and framework-default betas `(0.9, 0.95)`. The existing trainer uses a separate vision peak LR of `1e-6`; both language and vision groups receive the same scheduler multiplier. These settings are retained explicitly in the training YAMLs.

</details>

<details>
<summary>3. Resume training and save logs</summary>

Resume a Qwen2.5 run with `--train.load_checkpoint_path auto`, or pass an explicit DCP checkpoint directory. The Qwen3 entry retains the original script's `auto` resume setting.

Set `LOG_FILE` to change the launcher's default `log.txt`. If the checkout is on shared storage, use a separate log file per node. Use a fresh output directory for each unrelated experiment.

</details>

<details>
<summary>4. Extraction/reasoning and short-data ablations</summary>

Extraction-to-reasoning mixtures are in [scripts/qwen_vl_mix_yaml/](scripts/qwen_vl_mix_yaml/): `0_10`, `2_8`, `4_6`, `6_4`, `8_2`, and `10_0`. Select an edited mixture with `--data.train_path`. The `even` configuration uses equal task weights; it does not enforce a uniform sequence-length distribution.

Historical short-data mixtures are in [scripts/qwen_vl_short_mix_yaml/](scripts/qwen_vl_short_mix_yaml/). Their long-data component is **6:4**, whereas the paper describes **8:2**. Their `weights` are sample probabilities derived from `token_weights / avg_len`; the loader consumes `weights` directly. Recalculate the probabilities for a new corpus. Original filenames and weights are retained, with the differences documented in the [reproduction notes](docs/reproduction_notes.md).

</details>

## Repository structure

```text
configs/mmprolong/                 Complete MMProLong training entries
configs/model_configs/qwen/        Model JSONs, including the 128K Qwen2.5 config
scripts/qwen_vl_job/               Training and checkpoint-export wrappers
scripts/qwen_vl_mix_yaml/          Main mixture and extraction/reasoning ablations
scripts/qwen_vl_short_mix_yaml/    Historical short-data ablations (6:4 long mix)
data_synthesis_doc_vqa/            Data-synthesis reference implementation
tasks/omni/train_qwen_vl.py        Qwen2.5-VL / Qwen3-VL training task
tasks/data/vlm_data_process.py     Qwen-VL sample transformations
veomni/                           Inherited framework and MMProLong modifications
tests/                            Framework tests and portable release checks
docs/reproduction_notes.md         Known paper/code differences to resolve
```

Shared VeOmni modules and their tests are retained because model registration, parallelism, and imports cross these modules. Unrelated standalone examples and obsolete experiment files have been removed. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and validation commands.

## Contacts

For questions about MMProLong, please open a [GitHub issue](https://github.com/zhaowei-wang-nlp/MMProLong/issues) or email `zwanggy@cse.ust.hk`.

## Citation

If you find MMProLong useful, please cite our paper:

```bibtex
@article{wang2026mmprolong,
  title={Training Long-Context Vision-Language Models Effectively with Generalization Beyond 128K Context},
  author={Wang, Zhaowei and Luo, Lishu and Duan, Haodong and Liu, Weiwei and Wu, Sijin and Luo, Ji and Yan, Shen and Peng, Shuai and Yuan, Sihang and Huang, Chaoyi and Lin, Yi and Song, Yangqiu},
  journal={arXiv preprint arXiv:2605.13831},
  year={2026},
  url={https://arxiv.org/abs/2605.13831}
}
```

## Acknowledgment

This codebase is forked from [VeOmni](https://github.com/ByteDance-Seed/VeOmni). We retain the upstream package name, copyright notices, and [original README](README_VeOmni.md). Please also acknowledge VeOmni when using the training framework; its citation is provided there. See [NOTICE](NOTICE) for attribution and the scope of the MMProLong modifications.

We thank the authors and maintainers of Qwen, MMLongBench, VLMEvalKit, FlashAttention, and PyTorch.

## License

See [LICENSE](LICENSE) for the inherited Apache 2.0 license and [NOTICE](NOTICE) for attribution. File-level third-party notices continue to apply. Model weights, source documents, and datasets retain their own licenses.

For vulnerability reports, follow [SECURITY.md](SECURITY.md).
