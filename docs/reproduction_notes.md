# Paper/code differences and release provenance

Reviewed against [arXiv:2605.13831](https://arxiv.org/html/2605.13831), especially Sections 3, 5.3, Appendix 8, and Table 6. The code baseline is repository commit `9b478d9` before release cleanup. **Maintainer decision: preserve the existing scripts' numeric settings and correct the paper later.** Moving these values into explicit training YAMLs does not resolve the following discrepancies.

## Differences to resolve in the paper

1. **Token budget.** The paper defines B = 2^30 and says 5B, implying 5,368,709,120 tokens. Both original launch scripts set `data.train_size=5_000_000_000`. The released YAMLs retain 5,000,000,000. With 32 × 131,072 nominal tokens per update and default zero packing margin/batch warmup, `TrainingArguments.compute_train_steps` returns 1,193 steps; the binary budget would yield 1,280. This is a step-budget calculation, not a measurement of actual packed tokens. Check the original training logs before revising the budget statement.

2. **Parallelism.** Table 6 and Appendix 8.2 say sequence parallel size 2 and FSDP size 4. The original scripts use `ulysses_parallel_size=2` and `data_parallel_shard_size=8`; the release preserves both. The corresponding code computes data-parallel size as world size / 2. At 64 GPUs, it produces 32 data-parallel workers and 4 replication groups. VeOmni also folds sequence parallelism into its FSDP mesh (`include_sp_in_fsdp=True`), so the actual FSDP sharding mesh spans 8 × 2 ranks. State both the configured dimensions and mesh convention in the revised paper. At 8 GPUs, the data-parallel size would be 4, which cannot be divided into shards of size 8. Overriding `data_parallel_shard_size=4` satisfies that topology check with Ulysses size 2; it does not establish that 128K training fits the available GPU memory. This is derived from the configuration checks, not a measured 8-GPU training result.

3. **Short-data ablations.** Section 5.3 says the long-context component is fixed at extraction:reasoning = 8:2. The existing `long_doc_vqa_6_4_short{20,40,60,80}.yaml` files use 6:4. For example, short40 has token weights `[0.18, 0.18, 0.24, 0.40]`, which normalize within long data to `[0.30, 0.30, 0.40]`. The filenames and weights remain unchanged. The short100 control contains only short data. Confirm experiment provenance before changing text, plots, or labels; these source files alone cannot establish which mixture generated each published result.

4. **Vision learning rate.** The paper describes a peak LR of 1e-5 and minimum LR of 1e-6. The task's `MyTrainingArguments` sets a separate vision peak LR of 1e-6, and `get_param_groups` assigns it to parameters whose names contain `visual`. The release makes that default explicit. Both groups receive the same scheduler multiplier, so the vision group's terminal LR is 1e-7. Verify whether the paper should describe separate language/vision rates.

5. **Source-corpus boundaries.** Original mixture paths were named `min32max49`, whereas the paper describes 32–50 pages. The postprocessor applies inclusive page bounds and defaults to a 124K upper token filter. The synthesis guide preserves the historical 32–49 example and documents both filters. Verify corpus statistics before deciding whether this is a naming convention or an actual sample-selection difference.

## Model configuration that needs run-asset verification

The original Qwen2.5 launcher reads `config_128K.json` from its externally staged model directory. That file was not included in the provided checkout, so its original RoPE settings cannot be verified from repository source alone.

The release provides `configs/model_configs/qwen/mmprolong_qwen25_vl_7b_128k.json`, derived from the public [Qwen2.5-VL-7B-Instruct configuration](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/blob/main/config.json), with only these changes:

- `rope_theta`: 1,000,000 → 4,000,000, as specified in the paper.
- `max_position_embeddings`: 128,000 in the downloaded public config → 131,072.
- `use_cache`: true → false for training.

The public config's 128,000 position limit should not be confused with the paper's description of the base model's 32K training context. The released JSON is a reconstruction, not a recovered original experiment file. Compare it with the original run's `model_assets/config.json` before claiming exact reproduction. Qwen3 continues to use its own pretrained config without the Qwen2.5 RoPE modification.

## Release behavior changes

- Original numerical launch settings are in `configs/mmprolong/`; wrapper paths remain available. W&B becomes opt-in, and user-editable local/shared paths replace internal storage paths and model-copy commands.
- The launcher honors standard `NNODES`, `NODE_RANK`, `MASTER_ADDR`, `MASTER_PORT`, and `NPROC_PER_NODE` without overwriting them from a private scheduler. Arguments are quoted and failures propagate through logging.
- YAML `data.mm_configs` now matches the task dataclass. The inherited examples spell it `mm_config`, which the parser silently ignores. The explicit values are the intended existing video defaults; the long-document recipe uses images.
- Checkpoint export uses the actual saved `model_assets` rather than copying and swapping a separate base-model config.
- The API provider, model, and credentials used for synthesis are supplied by environment variables. The private endpoint identifier is removed.
- Unrelated standalone examples, local environment/editor files, the duplicate model-card folder, obsolete documentation build configuration, and upstream-specific CI are removed. Shared VeOmni modules, file-level licensing notices, and framework tests remain.

## What is still needed for exact reproduction

- Original run assets/logs to resolve the discrepancies above and verify the reconstructed JSON.
- The original training corpus is not publicly released. The data generation pipeline can be used on another document collection, but the resulting corpus and metrics will differ. Final dataset statistics are needed to assess corpus differences; three source weights do not enforce a specific sequence-length distribution.
- Model weights, benchmark artifacts for the 256K/512K extensions, and pinned evaluation settings.
- Validation on the intended GPU cluster. Portable checks verify configuration structure and launcher behavior; they do not execute distributed training, checkpoint export on real weights, or the paid synthesis pipeline.

The [public repository](https://github.com/zhaowei-wang-nlp/MMProLong) starts from a clean snapshot of the release files. Original experiment history and local cleanup backups are retained in the development repository. Upstream attribution, the inherited license, and file-level third-party notices are included in the public snapshot.

## Local validation (2026-10-17)

- Ruff 0.13.1 lint/format checks passed on the release-owned Python surface.
- Seven portable configuration/launcher tests passed; Python syntax compilation, shell syntax checks, and local Markdown target checks passed.
- Transformers 4.57.1 loaded the reconstructed model JSON and exposed RoPE 4,000,000 and 131,072 positions. This is a configuration check in the available local environment, not a validation of the pinned GPU stack.
- Training dependency declarations and uv resolution settings are unchanged. An offline `uv 0.9.8 lock --check` could not finish because the referenced CUDA PyTorch wheel was absent from the cache. The lock file was not regenerated.
- Full training, inference metrics, real-checkpoint export, and paid API synthesis were not run locally.
