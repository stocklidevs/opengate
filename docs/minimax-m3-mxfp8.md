# MiniMax-M3-MXFP8 Notes

Date checked: 2026-07-03 UTC, 2026-07-02 America/New_York.

## Serving Target

Model:

- `MiniMaxAI/MiniMax-M3-MXFP8`
- Served as `MiniMax-M3-MXFP8`
- Quantization: MXFP8
- Model card: https://huggingface.co/MiniMaxAI/MiniMax-M3-MXFP8

The public model card describes MiniMax-M3 as a native multimodal MoE with about 428B total parameters, about 23B activated parameters, and a 1M context design. The MXFP8 repository is about 444 GB, so the GX10 required cache cleanup before even attempting to serve it.

## GX10 Preparation

Before the attempt, the GX10 had about 342 GB free and old root-owned Hugging Face cache directories for Qwen, GLM, and Kimi. Direct `rm -rf` failed because those files had been created by Docker as root. The cleanup used the existing vLLM image with `/bin/rm` as the entrypoint and removed only the old model cache directories. Free disk rose to about 560 GB and the Hugging Face cache dropped to about 90 MB.

## Initial vLLM Launch

Command shape:

```bash
docker run -d --name minimax_m3_mxfp8 --gpus all --ipc=host \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  MiniMaxAI/MiniMax-M3-MXFP8 \
  --served-model-name MiniMax-M3-MXFP8 \
  --trust-remote-code \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85 \
  --host 0.0.0.0 \
  --port 8000
```

vLLM accepted the model and custom architecture:

- Resolved architecture: `MiniMaxM3SparseForConditionalGeneration`
- Quantization: `mxfp8`
- Max model length: `65536`
- MiniMax sparse attention path selected
- MXFP8 MoE backend selected

The server failed during model construction before a usable `/v1/models` endpoint came up and before weight download began:

```text
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 4.50 GiB.
GPU 0 has a total capacity of 119.61 GiB of which 2.79 GiB is free.
Including non-PyTorch memory, this process has 112.40 GiB memory in use.
```

The model cache for `MiniMaxAI/MiniMax-M3-MXFP8` was only about 9.4 MB at this point, confirming this was a model-initialization memory failure rather than a completed weight-download failure.

## Offload Retry

The retry added vLLM memory-saving flags:

```bash
docker run -d --name minimax_m3_mxfp8 --gpus all --ipc=host \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:nightly-aarch64 \
  MiniMaxAI/MiniMax-M3-MXFP8 \
  --served-model-name MiniMax-M3-MXFP8 \
  --trust-remote-code \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85 \
  --cpu-offload-gb 8 \
  --kv-cache-dtype fp8 \
  --enforce-eager \
  --host 0.0.0.0 \
  --port 8000
```

vLLM accepted the flags and reported:

- `kv_cache_dtype = fp8`
- `enforce_eager = True`
- `cpu_offload_gb = 8.0`
- `Offloader set to UVAOffloader`

This got past the first argument/configuration boundary but saturated the GX10 memory during model construction:

```text
Mem: 119Gi total, 119Gi used, 581Mi free
Swap: 15Gi total, 2.9Gi used
```

After that, SSH became unresponsive and fresh connections timed out during banner exchange. The container never exposed a usable OpenAI-compatible endpoint, and no CSVQL benchmark was run.

## Decision

MiniMax-M3-MXFP8 is parked as deployment-blocked on the single-GPU GX10 setup. This is not a CSVQL capability result and not an OpenGate repair target. The current evidence says the public MXFP8 checkpoint is too large for this host before Codex, tool calling, or OpenGate behavior can be measured.

Rerun only if one of these changes:

- A smaller MiniMax coding-capable quantization becomes available.
- The model is served on hardware with substantially more usable memory.
- vLLM gains a serving path that can construct and offload this architecture without exhausting the host.
