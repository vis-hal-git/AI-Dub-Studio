"""Job data model."""

from datetime import datetime
from typing import List, Optional
from app.models.schemas import JobStatus, LanguageCode, SpeakerSegment, SpeakerInfo


class DubbingJob:
    """Represents a video dubbing job."""

    def __init__(
        self,
        job_id: str,
        video_path: str,
        source_language: LanguageCode,
        target_language: LanguageCode,
        preserve_background_audio: bool = True,
        original_filename: str = "",
    ):
        self.job_id = job_id
        self.video_path = str(video_path)
        self.source_language = source_language
        self.target_language = target_language
        self.preserve_background_audio = preserve_background_audio
        self.original_filename = original_filename

        # Status tracking
        self.status: JobStatus = JobStatus.PENDING
        self.progress: float = 0.0
        self.current_stage: Optional[str] = None
        self.error: Optional[str] = None

        # Processing results
        self.speakers_detected: Optional[List[SpeakerInfo]] = None
        self.transcript: Optional[List[SpeakerSegment]] = None
        self.translation: Optional[List[SpeakerSegment]] = None
        self.output_path: Optional[str] = None

        # Timestamps
        self.created_at: datetime = datetime.utcnow()
        self.updated_at: datetime = datetime.utcnow()
        self.completed_at: Optional[datetime] = None

    def update_status(self, status: JobStatus, progress: float, stage: str):
        """Update job status and progress."""
        self.status = status
        self.progress = progress
        self.current_stage = stage
        self.updated_at = datetime.utcnow()

    def mark_completed(self, output_path: str):
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.progress = 100.0
        self.output_path = output_path
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: str):
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.error = error
        self.updated_at = datetime.utcnow()
