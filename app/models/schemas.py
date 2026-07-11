"""Pydantic schemas for API models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LanguageCode(str, Enum):
    AUTO = "auto"
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    JAPANESE = "ja"
    CHINESE = "zh"
    KOREAN = "ko"
    ARABIC = "ar"
    HINDI = "hi"
    RUSSIAN = "ru"


class JobStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    TRANSLATING = "translating"
    SYNTHESIZING = "synthesizing"
    MIXING = "mixing"
    COMPLETED = "completed"
    FAILED = "failed"


class SpeakerSegment(BaseModel):
    speaker_id: str
    start_time: float
    end_time: float
    original_text: str
    translated_text: str
    voice_assigned: Optional[str] = None


class SpeakerInfo(BaseModel):
    speaker_id: str
    voice_assigned: str
    segment_count: int
    total_duration: float


class DubbingJobCreate(BaseModel):
    source_language: LanguageCode = LanguageCode.AUTO
    target_language: LanguageCode = LanguageCode.SPANISH


class DubbingJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    source_language: LanguageCode
    target_language: LanguageCode
    created_at: datetime


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(ge=0, le=100, description="Progress percentage")
    current_stage: Optional[str] = None
    speakers_detected: Optional[List[SpeakerInfo]] = None
    transcript: Optional[List[SpeakerSegment]] = None
    translation: Optional[List[SpeakerSegment]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
