#!/usr/bin/env python3
"""Download FlashVSR+ weights through hf-mirror or an explicit ModelScope repo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


FILES = {
    "turbo": ["turbo/dit.safetensors", "turbo/lq_proj_in.safetensors"],
    "base": ["base/dit.safetensors", "base/lq_proj_in.safetensors"],
    "v1": ["v1/dit.safetensors", "v1/lq_proj_in.safetensors"],
}
SHARED = ["TCDecoder.ckpt", "Wan2.1_VAE.pth"]
V1_REPO = "JunhaoZhuang/FlashVSR-v1.1"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["turbo", "base", "v1", "all"], default="turbo")
    parser.add_argument("--local-dir", type=Path, default=root / "ckpts")
    parser.add_argument("--repo-id", default="ruchangyao/FlashVSR_plus")
    parser.add_argument("--endpoint", default=os.getenv("HF_ENDPOINT", "https://hf-mirror.com"))
    parser.add_argument("--modelscope-id", default=None, help="optional ModelScope mirror repo")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    # Xet CAS can return 401 on otherwise public repositories when the
    # mirror-issued token is not accepted. Standard LFS/CDN is more reliable
    # behind the domestic mirror and can still be proxied per-command.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    if os.getenv("FLASHVSR_USE_PROXY", "0") == "1":
        proxy_url = (
            os.getenv("FLASHVSR_PROXY_URL")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("HTTP_PROXY")
        )
        if not proxy_url:
            raise SystemExit(
                "FLASHVSR_USE_PROXY=1 requires FLASHVSR_PROXY_URL or HTTP(S)_PROXY"
            )
        os.environ.setdefault("HTTP_PROXY", proxy_url)
        os.environ.setdefault("HTTPS_PROXY", proxy_url)
        os.environ.setdefault("ALL_PROXY", proxy_url)
    else:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)
    modes = ["turbo", "base", "v1"] if args.mode == "all" else [args.mode]
    expected = [name for mode in modes for name in FILES[mode]] + SHARED
    if not args.verify_only:
        if args.modelscope_id:
            from modelscope import snapshot_download
            snapshot_download(args.modelscope_id, local_dir=str(args.local_dir), cache_dir=str(root / ".modelscope-cache"))
        else:
            os.environ["HF_ENDPOINT"] = args.endpoint
            from huggingface_hub import snapshot_download
            if os.getenv("HF_HUB_DISABLE_XET", "0") == "1":
                # huggingface_hub 2.x checks package availability separately
                # from HF_HUB_DISABLE_XET. Force the documented fallback to
                # ordinary HTTP/LFS for mirror-issued URLs.
                import huggingface_hub.utils._runtime as _runtime
                import huggingface_hub.file_download as _file_download
                _runtime.is_xet_available = lambda: False
                _file_download.is_xet_available = lambda: False
            snapshot_download(
                repo_id=args.repo_id,
                revision="main",
                local_dir=str(args.local_dir),
                allow_patterns=[name for name in expected if not name.startswith("v1/")],
                max_workers=4,
            )
            if "v1" in modes:
                snapshot_download(
                    repo_id=V1_REPO,
                    revision="main",
                    local_dir=str(args.local_dir / "v1"),
                    allow_patterns=["dit.safetensors", "lq_proj_in.safetensors"],
                    max_workers=2,
                )
    missing = [name for name in expected if not (args.local_dir / name).is_file()]
    if missing:
        raise SystemExit("missing model files:\n" + "\n".join(missing))
    for name in expected:
        path = args.local_dir / name
        print(f"verified {name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
