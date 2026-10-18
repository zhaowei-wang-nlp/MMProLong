# Paper/code differences and release provenance

Reviewed against [arXiv:2605.13831](https://arxiv.org/html/2605.13831) and the NeurIPS 2026 camera-ready manuscript. The code baseline is repository commit `9b478d9` before release cleanup. Earlier releases preserved the original scripts' numeric settings. On 2026-10-18, the maintainer requested that the released short-data mixtures and parallelism configuration be aligned with the paper.

## Configuration updates aligned with the paper

- **Parallelism.** Both released training entries now use `ulysses_parallel_size=2` and `data_parallel_shard_size=4`, replacing the historical shard setting of 8. At 64 GPUs, the data-parallel dimension is 32 and the automatically inferred replication count is 8. At 8 GPUs, those dimensions are 4 and 1, respectively. VeOmni folds sequence parallelism into the FSDP sharding mesh (`include_sp_in_fsdp=True`), so each sharding group spans 4 × 2 ranks; the configured shard dimension and the combined mesh size are distinct. These are configuration/topology checks, not measurements of GPU memory usage or training throughput.

- **Short-data ablations.** The released `long_doc_vqa_8_2_short{20,40,60,80}.yaml` files now keep extraction:reasoning = 8:2 within the long-data token budget, matching Section 5.3. They replace the historical `long_doc_vqa_6_4_short*.yaml` files. Both `token_weights` and the loader's actual sample `weights` have been updated. For short40, token weights are `[0.24, 0.24, 0.12, 0.40]`, giving `[0.40, 0.40, 0.20]` within long data. Sample probabilities are normalized from `token_weights / avg_len`; recompute them using the average lengths of a new corpus. The renamed short100 control still contains only short data.

These changes align the released configuration with the manuscript. Historical training settings remain available in Git history; linking published scores to their exact runs still requires the original experiment logs.

## Remaining paper/code details

1. **Token budget.** The paper defines B = 2^30 and says 5B, implying 5,368,709,120 tokens. Both original launch scripts set `data.train_size=5_000_000_000`. The released YAMLs retain 5,000,000,000. With 32 × 131,072 nominal tokens per update and default zero packing margin/batch warmup, `TrainingArguments.compute_train_steps` returns 1,193 steps; the binary budget would yield 1,280. This is a step-budget calculation, not a measurement of actual packed tokens. Check the original training logs before revising the budget statement.

2. **Vision learning rate.** The paper describes a peak LR of 1e-5 and minimum LR of 1e-6. The task's `MyTrainingArguments` sets a separate vision peak LR of 1e-6, and `get_param_groups` assigns it to parameters whose names contain `visual`. The release makes that default explicit. Both groups receive the same scheduler multiplier, so the vision group's terminal LR is 1e-7. Verify whether the paper should describe separate language/vision rates.

3. **Source-corpus boundaries.** Original mixture paths were named `min32max49`, whereas the paper describes 32–50 pages. The postprocessor applies inclusive page bounds and defaults to a 124K upper token filter. The synthesis guide preserves the historical 32–49 example and documents both filters. Verify corpus statistics before deciding whether this is a naming convention or an actual sample-selection difference.

## Original model configurations

The original Qwen2.5-VL 128K training configurations supplied by the maintainer on 2026-10-18 are included byte-for-byte:

- [Qwen2.5-VL-3B](../configs/model_configs/qwen/mmprolong_qwen25_vl_3b_128k.json), supplied as `Qwen2.5_3B_config_128K.json`.
- [Qwen2.5-VL-7B](../configs/model_configs/qwen/mmprolong_qwen25_vl_7b_128k.json), supplied as `Qwen2.5_7B_config_128K.json`. The main training YAML already references this path.

Both configurations use `rope_theta=4000000`, `max_position_embeddings=131072`, `sliding_window=131072`, `use_sliding_window=false`, and `use_cache=true`. Their architecture dimensions are specific to the 3B and 7B backbones and must be paired with matching model weights and tokenizers.

This implements the **NTK-aware 32K-to-128K context extension** through a fixed mRoPE base adjustment: the public Qwen2.5-VL-3B and 7B base configurations use `rope_theta=1000000`, while these training configurations use `rope_theta=4000000` (4×). The original mRoPE sections `[16, 24, 24]` remain unchanged. The training entry passes the selected JSON through `model.config_path` to the model loader and logs the effective RoPE base and position limit after loading.

The earlier release's derived 7B JSON differed from the supplied original in only two fields: `sliding_window` was 32768 and `use_cache` was false. These values are now restored to the original file. During training, the existing Qwen2.5-VL implementation disables caching when gradient checkpointing is active.

Qwen3-VL retains its native 256K model configuration unchanged. Its existing MMProLong recipe still trains with a 128K sequence limit; no Qwen3 configuration or launch script was changed when adding these files.

## Release behavior changes

- Training settings are in `configs/mmprolong/`, including the parallelism update described above; wrapper paths remain available. W&B becomes opt-in, and user-editable local/shared paths replace internal storage paths and model-copy commands.
- The launcher honors standard `NNODES`, `NODE_RANK`, `MASTER_ADDR`, `MASTER_PORT`, and `NPROC_PER_NODE` without overwriting them from a private scheduler. Arguments are quoted and failures propagate through logging.
- YAML `data.mm_configs` now matches the task dataclass. The inherited examples spell it `mm_config`, which the parser silently ignores. The explicit values are the intended existing video defaults; the long-document recipe uses images.
- Checkpoint export uses the actual saved `model_assets` rather than copying and swapping a separate base-model config.
- The API provider, model, and credentials used for synthesis are supplied by environment variables. The private endpoint identifier is removed.
- Unrelated standalone examples, local environment/editor files, the duplicate model-card folder, obsolete documentation build configuration, and upstream-specific CI are removed. Shared VeOmni modules, file-level licensing notices, and framework tests remain.

## What is still needed for exact reproduction

- Experiment logs that associate each reported result with its actual training arguments, to resolve the remaining paper/code differences above. The original 3B and 7B model JSONs are now available.
- The original training corpus is not publicly released. The data generation pipeline can be used on another document collection, but the resulting corpus and metrics will differ. Final dataset statistics are needed to assess corpus differences; three source weights do not enforce a specific sequence-length distribution.
- Model weights, benchmark artifacts for the 256K/512K extensions, and pinned evaluation settings.
- Validation on the intended GPU cluster. Portable checks verify configuration structure and launcher behavior; they do not execute distributed training, checkpoint export on real weights, or the paid synthesis pipeline.

The [public repository](https://github.com/zhaowei-wang-nlp/MMProLong) starts from a clean snapshot of the release files. Original experiment history and local cleanup backups are retained in the development repository. Upstream attribution, the inherited license, and file-level third-party notices are included in the public snapshot.

## Validation

- Ruff 0.13.1 lint/format checks passed on the release-owned Python surface.
- Nine portable configuration/launcher tests passed, including explicit 7B 128K JSON selection and the 3B config override. Python syntax compilation, shell syntax checks, and local Markdown target checks passed.
- On 2026-10-18, both original model JSONs were compared byte-for-byte with the files supplied by the maintainer. Transformers 4.57.1 loaded both configurations with the expected architecture, 128K position limit, and RoPE base. With `use_sliding_window=false`, Transformers normalizes the effective window to `None`; the original JSON values remain intact. This checks configuration loading, not the pinned GPU training stack.
- Training dependency declarations and uv resolution settings are unchanged. An offline `uv 0.9.8 lock --check` could not finish because the referenced CUDA PyTorch wheel was absent from the cache. The lock file was not regenerated.
- Full training, inference metrics, real-checkpoint export, and paid API synthesis were not run locally.

- On 2026-10-18, release checks were extended to recover token proportions from sample probabilities and corpus mean lengths for all short-data mixtures. This catches stale loader weights when token ratios change.
