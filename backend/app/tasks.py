from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery("file-converter", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    # Restart each worker process after 10 tasks to reclaim memory from LibreOffice and ffmpeg subprocesses that leak over time.
    worker_max_tasks_per_child=10,

    # Never let a worker prefetch more than one task. Without this, a worker running a 2GB video conversion can grab a second task and OOM.
    worker_prefetch_multiplier=1,

    # Ack only after the task completes so a worker crash re-queues the task.
    task_acks_late=True,

    # Re-queue tasks whose worker dies mid-execution (OOM kill, SIGKILL).
    task_reject_on_worker_lost=True,

    # Hard wall-clock limit per task: 30 min. Worker is SIGKILL'd after this.
    # Soft limit fires 5 min earlier and raises SoftTimeLimitExceeded inside he task, allowing clean-up before the hard kill.
    task_time_limit=1800,
    task_soft_time_limit=1500,

    # Expire tasks that were never picked up (e.g. worker was down) after 2h.
    task_expires=7200,

    # Periodic tasks (cleanup scheduler)
    beat_schedule={
        "cleanup-orphaned-files": {
            "task": "app.tasks.cleanup_orphaned_files",
            "schedule": crontab(minute="*/30"),
        },
    },
)


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
            raise self.retry(exc=exc, countdown=10)
        except self.MaxRetriesExceededError:
            if job is not None:
                job.status = "error"
                job.error_message = str(exc)[:512]
                db.commit()
    finally:
        db.close()


@celery_app.task
def cleanup_orphaned_files() -> None:
    """
    Delete files and DB records for jobs that were never downloaded or are stuck.

    Runs every 30 minutes via Celery Beat. Handles three cases:
      1. Jobs in pending/converting/done state older than MAX_AGE_HOURS (never finished
         or finished but never downloaded).
      2. Jobs stuck in "converting" longer than the task time limit (worker crashed
         mid-task without updating the DB).
      3. Files on disk with no matching DB record (worker crashed before creating
         the job row, or a previous cleanup run was interrupted).
    """
    from app.models import Job, SessionLocal

    MAX_AGE_HOURS = 2
    # A job stuck in "converting" beyond task_time_limit + buffer is a dead worker.
    STUCK_CONVERTING_MINUTES = 35

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_CONVERTING_MINUTES)

    with SessionLocal() as db:
        # 1. Stale finished/pending jobs not yet downloaded
        stale = db.query(Job).filter(
            Job.created_at < cutoff,
            Job.status.in_(["pending", "done"]),
        ).all()

        for job in stale:
            settings.upload_dir.joinpath(job.stored_filename).unlink(missing_ok=True)
            if job.output_filename:
                settings.output_dir.joinpath(job.output_filename).unlink(missing_ok=True)
            db.delete(job)

        # 2. Jobs stuck in "converting" — worker died without updating status
        stuck = db.query(Job).filter(
            Job.status == "converting",
            Job.created_at < stuck_cutoff,
        ).all()

        for job in stuck:
            job.status = "error"
            job.error_message = "Conversion timed out or worker crashed"
            logger.warning("Marking stuck job %s as error", job.id)

        db.commit()
        logger.info(
            "Cleanup: removed %d stale jobs, marked %d stuck jobs as error",
            len(stale),
            len(stuck),
        )

    # 3. Orphaned files on disk with no DB record (defensive sweep)
    with SessionLocal() as db:
        db_uploads: set[str] = set()
        db_outputs: set[str] = set()
        for row in db.query(Job.stored_filename, Job.output_filename).all():
            db_uploads.add(row.stored_filename)
            if row.output_filename:
                db_outputs.add(row.output_filename)

    age_cutoff = timedelta(hours=MAX_AGE_HOURS)
    now = datetime.now()

    for f in settings.upload_dir.glob("*"):
        if f.name not in db_uploads:
            age = now - datetime.fromtimestamp(f.stat().st_mtime)
            if age > age_cutoff:
                f.unlink()
                logger.info("Deleted orphaned upload: %s", f.name)

    for f in settings.output_dir.glob("*"):
        if f.name not in db_outputs:
            age = now - datetime.fromtimestamp(f.stat().st_mtime)
            if age > age_cutoff:
                f.unlink()
                logger.info("Deleted orphaned output: %s", f.name)