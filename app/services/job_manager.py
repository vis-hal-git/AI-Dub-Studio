"""Job manager service - orchestrates the dubbing pipeline."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.models.job import DubbingJob
from app.models.schemas import JobStatus, LanguageCode
from app.services.pipeline import DubbingPipeline
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobManager:
    """Manages video dubbing jobs."""

    def __init__(self):
        self._jobs: Dict[str, DubbingJob] = {}
        self._pipeline = DubbingPipeline()

    async def create_job(
        self,
        job_id: str,
        video_path: Path,
        source_language: LanguageCode,
        target_language: LanguageCode,

        original_filename: str,
    ) -> DubbingJob:
        """Create and store a new dubbing job."""
        job = DubbingJob(
            job_id=job_id,
            video_path=video_path,
            source_language=source_language,
            target_language=target_language,

            original_filename=original_filename,
        )
        self._jobs[job_id] = job
        logger.info(f"Job created: {job_id}")
        return job

    async def get_job(self, job_id: str) -> Optional[DubbingJob]:
        """Retrieve a job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self) -> List[DubbingJob]:
        """List all jobs."""
        return list(self._jobs.values())

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job and clean up its files."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        # Clean up files
        try:
            if Path(job.video_path).exists():
                Path(job.video_path).unlink()
            if job.output_path and Path(job.output_path).exists():
                Path(job.output_path).unlink()
        except Exception as e:
            logger.warning(f"Failed to clean up files for job {job_id}: {e}")

        del self._jobs[job_id]
        logger.info(f"Job deleted: {job_id}")
        return True

    async def process_job(self, job_id: str):
        """Process a dubbing job through the full pipeline."""
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f"Job not found for processing: {job_id}")
            return

        logger.info(f"Starting processing for job: {job_id}")

        try:
            output_path = await self._pipeline.run(job)
            job.mark_completed(str(output_path))
            logger.info(f"Job completed: {job_id} -> {output_path}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job failed: {job_id} - {error_msg}", exc_info=True)
            job.mark_failed(error_msg)
