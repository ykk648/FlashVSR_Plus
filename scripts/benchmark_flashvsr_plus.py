#!/usr/bin/env python3
"""Run one real inference and record wall time/peak CUDA memory as JSON."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch

from inference import InferenceRequest, build_inference_pipeline
from inference.presets import model_paths_for_mode, stream_config_for_mode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["turbo", "base", "v1"], default="turbo")
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--decode-every", default="auto")
    parser.add_argument("--cache-offload-mode", choices=["auto", "never", "always"], default="auto")
    parser.add_argument("--offload-original-cache", action="store_true")
    parser.add_argument("--attn-kernel", choices=["auto", "sdpa", "triton_block_sparse"], default="auto")
    parser.add_argument("--json", dest="json_path", type=Path, default=None)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable; run with GPU access/提权")
    device = torch.device(args.device)
    torch.cuda.set_device(device)
    config = stream_config_for_mode(
        args.mode,
        device=str(device),
        decode_every=args.decode_every,
        cache_offload_mode=args.cache_offload_mode,
        offload_original_cache=args.offload_original_cache,
        attn_kernel=args.attn_kernel,
    )
    pipeline = build_inference_pipeline(config, model_paths_for_mode(Path.cwd(), args.mode))
    torch.cuda.synchronize(device)
    torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()
    result = pipeline.infer(InferenceRequest(input_path=args.input, output_path=args.output, height=args.height, width=args.width, max_frames=args.max_frames))
    torch.cuda.synchronize(device)
    seconds = time.perf_counter() - start
    report = {
        "mode": args.mode, "device": str(device), "input": args.input, "output": args.output,
        "frames": result.frames, "seconds": seconds,
        "frames_per_second": result.frames / seconds if seconds else 0,
        "gpu_memory_peak_allocated_mib": torch.cuda.max_memory_allocated(device) / 2**20,
        "gpu_memory_peak_reserved_mib": torch.cuda.max_memory_reserved(device) / 2**20,
        "metadata": result.metadata,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
