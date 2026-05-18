"""
Background ingestion queue.

Files uploaded via the API are saved to disk immediately and then submitted
here as jobs.  A single daemon thread picks jobs off the queue one at a time
and calls index_file() so the HTTP request can return instantly.

Usage
-----
    from backend.ingestion.ingestion_queue import submit_job, get_job, list_jobs, start_worker

    # Call once at startup:
    start_worker()

    # Queue a file for ingestion:
    job_id = submit_job(file_path=Path("/data/offer.docx"), collection_name="boilerplate")

    # Poll from the frontend:
    job = get_job(job_id)   # returns IngestionJob | None
"""
from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional

from backend.ingestion.document_loader import index_file

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"


@dataclass
class IngestionJob:
    job_id:          str
    file_path:       Path
    collection_name: str
    status:          JobStatus = JobStatus.PENDING
    chunks_added:    int       = 0
    error:           Optional[str] = None
    queued_at:       str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at:     Optional[str] = None


# ── Internal state ────────────────────────────────────────────────────────────

_job_queue: queue.Queue[IngestionJob] = queue.Queue()
_jobs: dict[str, IngestionJob] = {}          # job_id → IngestionJob
_jobs_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def submit_job(file_path: Path, collection_name: str) -> str:
    """Queue a file for background ingestion. Returns the new job_id immediately."""
    job = IngestionJob(
        job_id=str(uuid.uuid4()),
        file_path=file_path,
        collection_name=collection_name,
    )
    with _jobs_lock:
        _jobs[job.job_id] = job
    _job_queue.put(job)
    logger.info("Queued %s → %s  (%s)", file_path.name, collection_name, job.job_id)
    return job.job_id


def get_job(job_id: str) -> Optional[IngestionJob]:
    """Return the IngestionJob for the given id, or None if not found."""
    with _jobs_lock:
        return _jobs.get(job_id)


def list_jobs() -> list[IngestionJob]:
    """Return all jobs (any status), newest first."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    return sorted(jobs, key=lambda j: j.queued_at, reverse=True)


def queue_size() -> int:
    """Number of jobs currently waiting in the queue (not yet started)."""
    return _job_queue.qsize()


def start_worker() -> None:
    """Start the background worker thread (idempotent — safe to call multiple times)."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, daemon=True, name="ingestion-worker")
        t.start()
        _worker_started = True
        logger.info("Background worker started.")


# ── Worker loop ───────────────────────────────────────────────────────────────

def _worker_loop() -> None:
    while True:
        job: IngestionJob = _job_queue.get()   # blocks until a job arrives
        try:
            logger.info("Processing %s …", job.file_path.name)
            with _jobs_lock:
                job.status = JobStatus.PROCESSING

            chunks = index_file(job.file_path, job.collection_name)

            with _jobs_lock:
                job.chunks_added = chunks
                job.status = JobStatus.DONE
                job.finished_at = datetime.utcnow().isoformat()

            logger.info("Done  %s  (%d chunks)", job.file_path.name, chunks)

        except Exception as exc:
            with _jobs_lock:
                job.status = JobStatus.FAILED
                job.error  = str(exc)
                job.finished_at = datetime.utcnow().isoformat()
            logger.error("FAILED %s: %s", job.file_path.name, exc, exc_info=True)

        finally:
            _job_queue.task_done()
