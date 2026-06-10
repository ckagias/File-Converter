from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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
    id: int
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_job_or_404(db: Session, job_id: int) -> Job:
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

    data = await file.read()
    file_size = len(data)

    category = EXT_CATEGORY.get(src_ext, "document")
    limit_bytes = CATEGORY_SIZE_LIMITS_MB.get(category, settings.max_file_size_mb) * 1024 * 1024
    if file_size > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size for {category} is {CATEGORY_SIZE_LIMITS_MB.get(category)} MB",
        )

    stored_name = f"{uuid.uuid4()}.{src_ext}"
    (settings.upload_dir / stored_name).write_bytes(data)

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
def job_status(job_id: int, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = _get_job_or_404(db, job_id)
    return JobStatusResponse(
        status=job.status,
        output_filename=job.output_filename,
        error_message=job.error_message,
    )


@app.get("/files/{job_id}/download")
def download_file(job_id: int, db: Session = Depends(get_db)) -> Response:
    job = _get_job_or_404(db, job_id)
    if job.status != "done" or not job.output_filename:
        raise HTTPException(status_code=400, detail="File not ready")
    path = settings.output_dir / job.output_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    filename = job.output_filename
    data = path.read_bytes()

    (settings.upload_dir / job.stored_filename).unlink(missing_ok=True)
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
