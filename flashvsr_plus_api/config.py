from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _paths(name: str, default: str) -> tuple[Path, ...]:
    raw = os.getenv(name, default)
    values = tuple(Path(item).expanduser().resolve() for item in raw.split(":") if item.strip())
    if not values:
        raise ValueError(f"{name} must contain at least one path")
    return values


@dataclass(frozen=True)
class Settings:
    repo_root: Path = REPO_ROOT
    device: str = os.getenv("FLASHVSR_PLUS_DEVICE", "cuda:0")
    host: str = os.getenv("FLASHVSR_PLUS_HOST", "0.0.0.0")
    port: int = int(os.getenv("FLASHVSR_PLUS_PORT", "18303"))
    runtime_root: Path = Path(
        os.getenv("FLASHVSR_PLUS_RUNTIME_ROOT", REPO_ROOT / "runtime/api")
    ).expanduser().resolve()
    allowed_input_roots: tuple[Path, ...] = _paths(
        "FLASHVSR_PLUS_ALLOWED_INPUT_ROOTS", os.fspath(REPO_ROOT / "examples")
    )
    max_frames: int = int(os.getenv("FLASHVSR_PLUS_MAX_FRAMES", "300"))
    max_target_pixels: int = int(os.getenv("FLASHVSR_PLUS_MAX_TARGET_PIXELS", "8294400"))
    max_upload_bytes: int = int(os.getenv("FLASHVSR_PLUS_MAX_UPLOAD_BYTES", str(8 * 1024**3)))
    default_mode: str = os.getenv("FLASHVSR_PLUS_DEFAULT_MODE", "turbo")
    decode_every: str = os.getenv("FLASHVSR_PLUS_DECODE_EVERY", "auto")

    @property
    def jobs_dir(self) -> Path:
        return self.runtime_root / "jobs"

    @property
    def outputs_dir(self) -> Path:
        return self.runtime_root / "outputs"

    @property
    def uploads_dir(self) -> Path:
        return self.runtime_root / "uploads"

    @property
    def effective_input_roots(self) -> tuple[Path, ...]:
        return self.allowed_input_roots + (self.uploads_dir,)

    @property
    def allowed_output_roots(self) -> tuple[Path, ...]:
        return self.effective_input_roots + (self.outputs_dir,)

    def checkpoint_files_for(self, mode: str) -> tuple[Path, Path]:
        directory = self.repo_root / "ckpts" / mode.lower()
        return directory / "dit.safetensors", directory / "lq_proj_in.safetensors"

    def mode_available(self, mode: str) -> bool:
        return all(path.is_file() for path in self.checkpoint_files_for(mode))
