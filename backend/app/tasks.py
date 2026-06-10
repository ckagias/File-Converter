from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery("file-converter", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(bind=True, max_retries=2)
def convert_file(self, job_id: int) -> None:
    from app.models import Job, SessionLocal
    from app.converters import handle_conversion

    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            return

        job.status = "converting"
        db.commit()

        ok, output_filename = handle_conversion(job.stored_filename, job.target_format)

        if ok:
            job.status = "done"
            job.output_filename = output_filename
        else:
            job.status = "error"
            job.error_message = f"Conversion from {job.source_format} to {job.target_format} failed"
        db.commit()

    except Exception as exc:
        db.rollback()
        try:
            # retry before giving up
            raise self.retry(exc=exc, countdown=10)
        except self.MaxRetriesExceededError:
            if job is not None:
                job.status = "error"
                job.error_message = str(exc)[:512]
                db.commit()
    finally:
        db.close()