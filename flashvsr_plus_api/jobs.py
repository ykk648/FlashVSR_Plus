from __future__ import annotations

import json
import logging
import queue
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .engine import FlashVSRPlusEngine
from .video import model_dimensions, probe_video, target_dimensions


LOGGER = logging.getLogger(__name__)
FINAL_STATES = {"completed", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = FlashVSRPlusEngine(settings)
        self.jobs: dict[str, dict[str, Any]] = {}
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        for path in self.settings.jobs_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if record.get("status") == "running":
                record.update(status="failed", stage="failed", error="process restarted", updated_at=utc_now(), finished_at=utc_now())
                self._persist(record)
            elif record.get("status") == "queued":
                self._queue.put(record["id"])
            self.jobs[record["id"]] = record
        self._thread = threading.Thread(target=self._worker, name="flashvsr-plus-gpu-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.engine.unload()

    @property
    def worker_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _path(self, raw: str, *, must_exist: bool, output: bool = False) -> Path:
        path = Path(raw).expanduser().resolve()
        roots = self.settings.allowed_output_roots if output else self.settings.effective_input_roots
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError("path is outside the configured allowlist")
        if must_exist and not path.is_file():
            raise ValueError(f"file does not exist: {path}")
        return path

    def create(
        self,
        input_path: str,
        scale: float,
        mode: str,
        output_path: str | None,
        width: int | None,
        height: int | None,
        frame_limit: int | None = None,
        source_name: str | None = None,
    ) -> dict:
        source = self._path(input_path, must_exist=True)
        info = probe_video(source)
        target_width, target_height = target_dimensions(info, scale, width, height)
        model_width, model_height = model_dimensions(target_width, target_height)
        if frame_limit is not None and (frame_limit < 1 or frame_limit > self.settings.max_frames):
            raise ValueError(f"frame_limit must be between 1 and {self.settings.max_frames}")
        processed_frames = min(info.frames, frame_limit) if frame_limit is not None else info.frames
        if model_width * model_height > self.settings.max_target_pixels:
            raise ValueError("target resolution exceeds configured pixel limit")
        mode = mode.lower()
        if mode not in {"turbo", "base", "v1"}:
            raise ValueError("mode must be turbo, base, or v1")
        if not self.settings.mode_available(mode):
            raise ValueError(
                f"mode {mode!r} weights are not installed under "
                f"{self.settings.repo_root / 'ckpts' / mode}"
            )
        job_id = uuid.uuid4().hex
        output = self._path(output_path, must_exist=False, output=True) if output_path else self.settings.outputs_dir / f"{job_id}.mp4"
        if output.suffix.lower() != ".mp4":
            raise ValueError("output_path must end with .mp4")
        if output.exists():
            raise ValueError(f"output already exists: {output}")
        now = utc_now()
        record = {
            "id": job_id, "status": "queued", "stage": "queued",
            "input_path": str(source), "output_path": str(output),
            "mode": mode, "scale": scale, "target": {"width": target_width, "height": target_height},
            "model_target": {"width": model_width, "height": model_height},
            "source": info.to_dict(), "processed_frames": processed_frames,
            "source_name": source_name or source.name,
            "download_name": f"{Path(source_name or source.name).stem}_flashvsr_{target_width}x{target_height}.mp4",
            "cancel_requested": False, "error": None,
            "created_at": now, "updated_at": now, "started_at": None, "finished_at": None,
        }
        with self._lock:
            self.jobs[job_id] = record
            self._persist(record)
        self._queue.put(job_id)
        return dict(record)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self.jobs.get(job_id)
            return dict(record) if record else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self.jobs.get(job_id)
            if record is None:
                return None
            if record["status"] in FINAL_STATES:
                return dict(record)
            record["cancel_requested"] = True
            if record["status"] == "queued":
                record.update(status="cancelled", stage="cancelled", finished_at=utc_now())
            record["updated_at"] = utc_now()
            self._persist(record)
            return dict(record)

    def _persist(self, record: dict[str, Any]) -> None:
        path = self.settings.jobs_dir / f"{record['id']}.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            record = self.jobs[job_id]
            record.update(values, updated_at=utc_now())
            self._persist(record)

    def _cancelled(self, job_id: str) -> bool:
        with self._lock:
            return bool(self.jobs[job_id]["cancel_requested"])

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            with self._lock:
                record = self.jobs.get(job_id)
                if record is None or record["status"] != "queued":
                    continue
                record.update(status="running", stage="loading_model", started_at=utc_now(), updated_at=utc_now())
                self._persist(record)
            try:
                stats = self.engine.upscale(
                    Path(record["input_path"]), Path(record["output_path"]),
                    probe_video(Path(record["input_path"])), record["mode"],
                    record["target"]["width"], record["target"]["height"],
                    record.get("processed_frames", record.get("source", {}).get("frames", self.settings.max_frames)),
                    progress=lambda stage: self._update(job_id, stage=stage),
                    cancelled=lambda: self._cancelled(job_id),
                )
                self._update(job_id, status="completed", stage="completed", metrics=stats, output_bytes=Path(record["output_path"]).stat().st_size, finished_at=utc_now())
            except InterruptedError as error:
                Path(record["output_path"]).unlink(missing_ok=True)
                self._update(job_id, status="cancelled", stage="cancelled", error=str(error), finished_at=utc_now())
            except BaseException as error:
                LOGGER.error("FlashVSR+ job %s failed\n%s", job_id, traceback.format_exc())
                Path(record["output_path"]).unlink(missing_ok=True)
                self._update(job_id, status="failed", stage="failed", error=f"{type(error).__name__}: {error}", finished_at=utc_now())
