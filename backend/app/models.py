from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    output_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)
    target_format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)