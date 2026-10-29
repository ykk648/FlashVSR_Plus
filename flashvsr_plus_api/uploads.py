from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from .config import Settings
from .video import VideoInfo, model_dimensions, probe_video, target_dimensions


ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
SCALE_CHOICES = (1.5, 2.0, 3.0, 4.0)
OUTPUT_HEIGHT_CHOICES = (720, 1080, 2048)


def _safe_name(name: str) -> str:
    return Path(name.replace("\\", "/")).name.strip() or "video.mp4"


def _fit_dimensions(info: VideoInfo, pixel_limit: int) -> tuple[int, int]:
    ratio = info.width / info.height
    height = int(math.sqrt(pixel_limit / ratio))
    width = int(height * ratio)
    width = max(128, width // 128 * 128)
    height = max(128, height // 128 * 128)
    while width * height > pixel_limit and (width > 128 or height > 128):
        if width / max(height, 1) > ratio and width > 128:
            width -= 128
        elif height > 128:
            height -= 128
        else:
            width -= 128
    return width, height


def analyze_video(info: VideoInfo, settings: Settings) -> dict[str, Any]:
    options = []
    for scale in SCALE_CHOICES:
        width, height = target_dimensions(info, scale, None, None)
        model_width, model_height = model_dimensions(width, height)
        model_pixels = model_width * model_height
        allowed = model_pixels <= settings.max_target_pixels
        if allowed and model_pixels <= 1_000_000:
            profile = "流畅，适合快速预览"
        elif allowed and model_pixels <= 4_200_000:
            profile = "均衡，耗时和画质折中"
        elif allowed:
            profile = "高负载，单任务可能需要数分钟"
        else:
            profile = "超过当前 8.29 MP 安全上限"
        options.append(
            {
                "scale": scale,
                "width": width,
                "height": height,
                "pixels": width * height,
                "model_width": model_width,
                "model_height": model_height,
                "model_pixels": model_pixels,
                "allowed": allowed,
                "profile": profile,
            }
        )

    resolution_options = []
    for output_height in OUTPUT_HEIGHT_CHOICES:
        output_width = max(
            2,
            int(round((info.width * output_height / info.height) / 2.0)) * 2,
        )
        model_width, model_height = model_dimensions(output_width, output_height)
        model_pixels = model_width * model_height
        allowed = model_pixels <= settings.max_target_pixels
        if output_height < info.height:
            profile = "低于输入高度，不建议作为超分目标"
        elif output_height == info.height:
            profile = "保持原始高度，可用于画质增强"
        elif model_pixels <= 1_200_000:
            profile = "速度优先，适合日常处理"
        elif model_pixels <= 4_500_000:
            profile = "均衡清晰度"
        else:
            profile = "高分辨率，耗时和显存占用更高"
        if not allowed:
            profile = "超过当前显存安全上限"
        resolution_options.append(
            {
                "label": f"{output_height}p",
                "height": output_height,
                "width": output_width,
                "scale": output_height / info.height,
                "pixels": output_width * output_height,
                "model_width": model_width,
                "model_height": model_height,
                "model_pixels": model_pixels,
                "allowed": allowed,
                "profile": profile,
            }
        )

    warnings: list[str] = []
    if info.frames > settings.max_frames:
        warnings.append(
            f"视频共 {info.frames} 帧；默认处理完整视频，耗时会随帧数增加。"
        )
    if not any(item["allowed"] for item in options):
        warnings.append("常用倍率都会超过当前显存安全上限，请使用建议的自定义尺寸。")
    fit_width, fit_height = _fit_dimensions(info, settings.max_target_pixels)
    duration = info.frames / info.fps if info.fps else 0.0
    return {
        "source": {**info.to_dict(), "duration_seconds": duration},
        "limits": {
            "max_frames": settings.max_frames,
            "max_target_pixels": settings.max_target_pixels,
            "alignment": 128,
        },
        "warnings": warnings,
        "requires_frame_limit": False,
        "offers_frame_limit": info.frames > settings.max_frames,
        "options": options,
        "resolution_options": resolution_options,
        "custom_suggestion": {
            "width": fit_width,
            "height": fit_height,
            "reason": "保持原始宽高比并控制在当前像素上限内",
        },
    }


class UploadStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def start(self) -> None:
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, upload_id: str) -> Path:
        if not UPLOAD_ID.fullmatch(upload_id):
            raise ValueError("invalid upload_id")
        return self.settings.uploads_dir / f"{upload_id}.json"

    async def save(
        self,
        filename: str,
        chunks: AsyncIterator[bytes],
        content_length: int | None,
    ) -> dict[str, Any]:
        original_name = _safe_name(filename)
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            supported = ", ".join(sorted(ALLOWED_VIDEO_SUFFIXES))
            raise ValueError(f"unsupported video format; supported: {supported}")
        if content_length is not None and content_length > self.settings.max_upload_bytes:
            raise ValueError("upload exceeds configured size limit")

        upload_id = uuid.uuid4().hex
        destination = self.settings.uploads_dir / f"{upload_id}{suffix}"
        temporary = self.settings.uploads_dir / f".{upload_id}.part"
        size = 0
        try:
            with temporary.open("wb") as stream:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise ValueError("upload exceeds configured size limit")
                    stream.write(chunk)
            if size == 0:
                raise ValueError("uploaded file is empty")
            temporary.replace(destination)
            info = probe_video(destination)
            analysis = analyze_video(info, self.settings)
            record = {
                "upload_id": upload_id,
                "filename": original_name,
                "path": str(destination),
                "bytes": size,
                **analysis,
            }
            metadata = self._metadata_path(upload_id)
            pending = metadata.with_suffix(".json.tmp")
            pending.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            pending.replace(metadata)
            return record
        except BaseException:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise

    def get(self, upload_id: str) -> dict[str, Any]:
        metadata = self._metadata_path(upload_id)
        if not metadata.is_file():
            raise ValueError("upload not found")
        try:
            record = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("upload metadata is unreadable") from error
        path = Path(record.get("path", "")).resolve()
        root = self.settings.uploads_dir.resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("uploaded video is missing")
        return record
