from __future__ import annotations

import uuid
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.converters import SUPPORTED_CONVERSIONS
from app.models import Base, Job, SessionLocal, engine

UPLOAD_DIR = Path("/app/uploads")
OUTPUT_DIR = Path("/app/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="File Converter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_CATEGORY_SIZE_LIMITS_MB = {
    "image":    50,
    "document": 100,
    "audio":    200,
    "video":    2000,
    "archive":  500,
}

_EXT_CATEGORY = {
    "jpg": "image", "jpeg": "image", "png": "image", "webp": "image",
    "bmp": "image", "tiff": "image", "svg": "image", "ico": "image",
    "pdf": "document", "docx": "document", "pptx": "document",
    "xlsx": "document", "odt": "document", "txt": "document",
    "mp3": "audio", "wav": "audio", "ogg": "audio",
    "flac": "audio", "aac": "audio", "m4a": "audio",
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video", "webm": "video",
    "zip": "archive", "7z": "archive", "gz": "archive",
}


@app.get("/formats")
def get_formats() -> dict:
    return SUPPORTED_CONVERSIONS


@app.post("/files/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    target_format: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    from app.tasks import convert_file

    original_name = file.filename or "upload"
    src_ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if src_ext not in SUPPORTED_CONVERSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported source format: {src_ext}")

    tgt = target_format.lower().lstrip(".")
    if tgt not in SUPPORTED_CONVERSIONS.get(src_ext, []):
        raise HTTPException(status_code=400, detail=f"Cannot convert {src_ext} to {tgt}")

    data = await file.read()
    file_size = len(data)

    category = _EXT_CATEGORY.get(src_ext, "document")
    limit_bytes = _CATEGORY_SIZE_LIMITS_MB.get(category, settings.max_file_size_mb) * 1024 * 1024
    if file_size > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size for {category} is {_CATEGORY_SIZE_LIMITS_MB.get(category)} MB",
        )

    stored_name = f"{uuid.uuid4()}.{src_ext}"
    (UPLOAD_DIR / stored_name).write_bytes(data)

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

    return {
        "id": job.id,
        "original_filename": job.original_filename,
        "source_format": job.source_format,
        "target_format": job.target_format,
        "status": job.status,
        "output_filename": job.output_filename,
        "file_size": job.file_size,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
    }


@app.get("/files/{job_id}/status")
def job_status(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = _get_job_or_404(db, job_id)
    return {"status": job.status, "output_filename": job.output_filename}


@app.get("/files/{job_id}/download")
def download_file(job_id: int, db: Session = Depends(get_db)) -> Response:
    job = _get_job_or_404(db, job_id)
    if job.status != "done" or not job.output_filename:
        raise HTTPException(status_code=400, detail="File not ready")
    path = OUTPUT_DIR / job.output_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    # read into memory so we can delete before responding
    filename = job.output_filename
    data = path.read_bytes()

    # clean up everything — files and job record
    (UPLOAD_DIR / job.stored_filename).unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    db.delete(job)
    db.commit()

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job