from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Callable

from .config import Settings
from .video import VideoInfo


ProgressCallback = Callable[[str], None]


class FlashVSRPlusEngine:
    """Keeps exactly one FlashVSR+ pipeline resident in the process."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pipeline = None
        self.loaded_mode: str | None = None
        self.torch = None

    @property
    def loaded(self) -> bool:
        return self.pipeline is not None

    def unload(self) -> None:
        self.pipeline = None
        self.loaded_mode = None
        gc.collect()
        if self.torch is not None and self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
            self.torch.cuda.ipc_collect()

    def load(self, mode: str) -> None:
        mode = mode.lower()
        if mode not in {"turbo", "base", "v1"}:
            raise ValueError("mode must be turbo, base, or v1")
        if self.pipeline is not None and self.loaded_mode == mode:
            return
        if self.pipeline is not None:
            self.unload()

        import torch

        self.torch = torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable to the FlashVSR+ API process")
        device = torch.device(self.settings.device)
        torch.cuda.set_device(device)
        from inference import build_inference_pipeline
        from inference.presets import model_paths_for_mode, stream_config_for_mode

        config = stream_config_for_mode(
            mode,
            device=str(device),
            decode_every=self.settings.decode_every,
            cache_offload_mode="auto",
            tiny_decoder_mode="auto",
            attn_kernel="auto",
            hardware_profile="auto",
        )
        paths = model_paths_for_mode(self.settings.repo_root, mode)
        self.pipeline = build_inference_pipeline(config, paths)
        self.loaded_mode = mode

    def upscale(
        self,
        input_path: Path,
        output_path: Path,
        info: VideoInfo,
        mode: str,
        width: int,
        height: int,
        max_frames: int,
        progress: ProgressCallback,
        cancelled: Callable[[], bool],
    ) -> dict:
        self.load(mode)
        assert self.pipeline is not None and self.torch is not None
        import torch
        from inference import InferenceRequest

        if cancelled():
            raise InterruptedError("Job cancelled before inference")
        progress("inference")
        device = torch.device(self.settings.device)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        started = time.perf_counter()
        result = self.pipeline.infer(
            InferenceRequest(
                input_path=input_path,
                output_path=output_path,
                height=height,
                width=width,
                max_frames=min(info.frames, max_frames),
            ),
            progress=progress,
            video_preset="veryfast",
        )
        torch.cuda.synchronize(device)
        elapsed = time.perf_counter() - started
        if cancelled():
            output_path.unlink(missing_ok=True)
            raise InterruptedError("Job cancelled after inference")
        return {
            "seconds": elapsed,
            "frames": result.frames,
            "fps": result.fps,
            "frames_per_second": result.frames / elapsed if elapsed else 0.0,
            "gpu_memory_allocated_mib": torch.cuda.memory_allocated(device) / 2**20,
            "gpu_memory_reserved_mib": torch.cuda.memory_reserved(device) / 2**20,
            "gpu_peak_memory_allocated_mib": torch.cuda.max_memory_allocated(device) / 2**20,
            "gpu_peak_memory_reserved_mib": torch.cuda.max_memory_reserved(device) / 2**20,
            "metadata": result.metadata,
        }
