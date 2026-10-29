#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import torch


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(f"root={root}")
    print(f"python={os.sys.version.split()[0]}")
    print(f"torch={torch.__version__}")
    print(f"cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            print(f"gpu{index}={props.name}, memory_mib={props.total_memory // 2**20}, cc={props.major}.{props.minor}")
    for module in ("fastapi", "uvicorn", "safetensors", "cv2", "imageio"):
        print(f"{module}={'ok' if importlib.util.find_spec(module) else 'missing'}")
    for path in (root / "ckpts/TCDecoder.ckpt", root / "ckpts/turbo/dit.safetensors", root / "ckpts/turbo/lq_proj_in.safetensors"):
        print(f"{path.relative_to(root)}={'ok' if path.is_file() else 'missing'}")


if __name__ == "__main__":
    main()
