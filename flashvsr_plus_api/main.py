from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .jobs import JobManager
from .uploads import UploadStore


settings = Settings()
manager = JobManager(settings)
uploads = UploadStore(settings)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class CreateJobRequest(BaseModel):
    input_path: str | None = Field(default=None, min_length=1)
    upload_id: str | None = Field(default=None, min_length=1)
    # Explicit width/height presets may represent more than 4x for very small
    # inputs. The model-canvas pixel limit remains the actual safety boundary.
    scale: float = Field(default=2.0, ge=1.0, le=16.0)
    mode: Literal["turbo", "base", "v1"] = "turbo"
    output_path: str | None = None
    width: int | None = Field(default=None, ge=128)
    height: int | None = Field(default=None, ge=128)
    frame_limit: int | None = Field(default=None, ge=1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    uploads.start()
    manager.start()
    try:
        yield
    finally:
        manager.stop()


app = FastAPI(title="FlashVSR+ API", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


def require_job(job_id: str) -> dict:
    value = manager.get(job_id)
    if value is None:
        raise HTTPException(status_code=404, detail="job not found")
    return value


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, object]:
    if not manager.worker_alive:
        raise HTTPException(status_code=503, detail="worker is not running")
    import torch
    return {
        "status": "ready" if torch.cuda.is_available() else "degraded",
        "cuda_available": bool(torch.cuda.is_available()),
        "model_loaded": manager.engine.loaded,
        "loaded_mode": manager.engine.loaded_mode,
        "device": settings.device,
        "available_modes": [mode for mode in ("turbo", "base", "v1") if settings.mode_available(mode)],
    }


@app.post("/api/jobs", status_code=202)
def create_job(request: CreateJobRequest) -> dict:
    try:
        if (request.input_path is None) == (request.upload_id is None):
            raise ValueError("provide exactly one of input_path or upload_id")
        source_name = None
        input_path = request.input_path
        if request.upload_id is not None:
            upload = uploads.get(request.upload_id)
            input_path = upload["path"]
            source_name = upload["filename"]
        assert input_path is not None
        return manager.create(
            input_path, request.scale, request.mode, request.output_path,
            request.width, request.height, request.frame_limit, source_name,
        )
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/uploads", status_code=201)
async def upload_video(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
) -> dict:
    raw_length = request.headers.get("content-length")
    try:
        content_length = int(raw_length) if raw_length else None
        return await uploads.save(filename, request.stream(), content_length)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return require_job(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    value = manager.cancel(job_id)
    if value is None:
        raise HTTPException(status_code=404, detail="job not found")
    return value


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = require_job(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="job is not completed")
    output = Path(job["output_path"])
    if not output.is_file():
        raise HTTPException(status_code=410, detail="output file is missing")
    return FileResponse(
        output,
        media_type="video/mp4",
        filename=job.get("download_name") or output.name,
    )
