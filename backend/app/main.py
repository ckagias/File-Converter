from __future__ import annotations

import unicodedata
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Generator
from urllib.parse import quote

import aiofiles
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.converters import (
    CATEGORY_SIZE_LIMITS_MB,
    EXT_CATEGORY,
    SUPPORTED_CONVERSIONS,
)
from app.models import Base, Job, SessionLocal, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="File Converter", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobResponse(BaseModel):
    id: str
    original_filename: str
    source_format: str
    target_format: str
    status: str
    output_filename: str | None
    file_size: int
    error_message: str | None
    created_at: str


class JobStatusResponse(BaseModel):
    status: str
    output_filename: str | None
    error_message: str | None


def _safe_content_disposition(filename: str) -> str:
    """Return a Content-Disposition filename value safe from header injection."""
    name = Path(filename).name
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C")
    ascii_safe = name.encode("ascii", errors="ignore").decode()
    encoded = quote(name, safe=" .-_~()")
    if ascii_safe == name:
        return f'attachment; filename="{ascii_safe}"'
    return f"attachment; filename*=UTF-8''{encoded}"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/formats")
def get_formats() -> dict:
    return SUPPORTED_CONVERSIONS


@app.post("/files/upload", status_code=status.HTTP_201_CREATED, response_model=JobResponse)
async def upload_file(
    file: UploadFile,
    target_format: str = Query(...),
    db: Session = Depends(get_db),
) -> JobResponse:
    from app.tasks import convert_file

    original_name = file.filename or "upload"
    src_ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if src_ext not in SUPPORTED_CONVERSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported source format: {src_ext}")

    tgt = target_format.lower().lstrip(".")
    if tgt not in SUPPORTED_CONVERSIONS.get(src_ext, []):
        raise HTTPException(status_code=400, detail=f"Cannot convert {src_ext} to {tgt}")

    category = EXT_CATEGORY.get(src_ext, "document")
    limit_mb = CATEGORY_SIZE_LIMITS_MB.get(category, settings.max_file_size_mb)
    limit_bytes = limit_mb * 1024 * 1024

    stored_name = f"{uuid.uuid4()}.{src_ext}"
    dest = settings.upload_dir / stored_name

    # Stream the upload to disk in 1 MB chunks so we never hold the full file
    # in memory — critical for 2 GB video uploads.
    file_size = 0
    try:
        async with aiofiles.open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > limit_bytes:
                    await f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size for {category} is {limit_mb} MB",
                    )
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc

    job = Job(
        original_filename=original_name,
        stored_filename=stored_name,
        source_format=src_ext,
        target_format=tgt,
        status="pending",
        file_size=file_size,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    task = convert_file.delay(job.id)
    job.task_id = task.id
    db.commit()
    db.refresh(job)

    return JobResponse(
        id=job.id,
        original_filename=job.original_filename,
        source_format=job.source_format,
        target_format=job.target_format,
        status=job.status,
        output_filename=job.output_filename,
        file_size=job.file_size,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
    )


@app.get("/files/{job_id}/status", response_model=JobStatusResponse)
def job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = _get_job_or_404(db, job_id)
    return JobStatusResponse(
        status=job.status,
        output_filename=job.output_filename,
        error_message=job.error_message,
    )


def _delete_job_files(job_id: str, upload_path: Path, output_path: Path) -> None:
    """Background task: delete files and DB record after download completes."""
    upload_path.unlink(missing_ok=True)
    output_path.unlink(missing_ok=True)
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            db.delete(job)
            db.commit()


@app.get("/files/{job_id}/download")
def download_file(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "done" or not job.output_filename:
        raise HTTPException(status_code=400, detail="File not ready")

    output_path = settings.output_dir / job.output_filename
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    upload_path = settings.upload_dir / job.stored_filename

    stem = Path(job.original_filename).stem
    download_name = f"{stem}.{job.target_format}"
    content_disposition = _safe_content_disposition(download_name)

    background_tasks.add_task(_delete_job_files, job.id, upload_path, output_path)

    response = FileResponse(
        path=output_path,
        media_type="application/octet-stream",
    )
    response.headers["Content-Disposition"] = content_disposition
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
