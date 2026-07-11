"""
Video Dubbing Platform - Main Application
LLM/AI Engineering Assignment 3
"""

import os
import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.models.schemas import (
    DubbingJobCreate,
    DubbingJobResponse,
    JobStatusResponse,
    LanguageCode,
)
from app.services.job_manager import JobManager
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

job_manager = JobManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Video Dubbing Platform started")
    yield
    logger.info("Video Dubbing Platform shutting down")


app = FastAPI(
    title="Video Dubbing Platform",
    description="Multi-speaker video translation and dubbing using AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "video-dubbing-platform",
    }


@app.post("/api/v1/jobs", response_model=DubbingJobResponse, tags=["Jobs"])
async def create_dubbing_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file to dub (max 10 minutes)"),
    source_language: LanguageCode = Form(LanguageCode.AUTO),
    target_language: LanguageCode = Form(LanguageCode.SPANISH),
    preserve_background_audio: bool = Form(True),
):
    """
    Create a new video dubbing job.

    - Accepts videos up to 10 minutes long
    - Identifies multiple speakers
    - Translates and dubs in target language
    - Preserves speaker identity and synchronization
    """
    # Validate file type
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {video.content_type}. Must be a video file.",
        )

    # Save uploaded video
    job_id = str(uuid.uuid4())
    upload_path = settings.UPLOAD_DIR / f"{job_id}_{video.filename}"

    try:
        content = await video.read()

        # Check file size (rough estimate: 10 min @ 720p ≈ 500MB)
        max_size = 500 * 1024 * 1024  # 500MB
        if len(content) > max_size:
            raise HTTPException(
                status_code=413,
                detail="File too large. Maximum size is 500MB (approx. 10 minutes).",
            )

        with open(upload_path, "wb") as f:
            f.write(content)

        logger.info(f"Video uploaded: {upload_path} ({len(content) / 1024 / 1024:.1f}MB)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Create job
    job = await job_manager.create_job(
        job_id=job_id,
        video_path=upload_path,
        source_language=source_language,
        target_language=target_language,
        preserve_background_audio=preserve_background_audio,
        original_filename=video.filename,
    )

    # Start processing in background
    background_tasks.add_task(job_manager.process_job, job_id)

    return DubbingJobResponse(
        job_id=job_id,
        status=job.status,
        message="Job created successfully. Processing started.",
        source_language=source_language,
        target_language=target_language,
        created_at=job.created_at,
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse, tags=["Jobs"])
async def get_job_status(job_id: str):
    """Get the status of a dubbing job."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job_id,
        status=job.status,
        progress=job.progress,
        current_stage=job.current_stage,
        speakers_detected=job.speakers_detected,
        transcript=job.transcript,
        translation=job.translation,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


@app.get("/api/v1/jobs", tags=["Jobs"])
async def list_jobs():
    """List all dubbing jobs."""
    jobs = await job_manager.list_jobs()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "progress": j.progress,
                "created_at": j.created_at,
                "source_language": j.source_language,
                "target_language": j.target_language,
            }
            for j in jobs
        ],
        "total": len(jobs),
    }


@app.get("/api/v1/jobs/{job_id}/download", tags=["Jobs"])
async def download_dubbed_video(job_id: str):
    """Download the dubbed video output."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job.status}",
        )

    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Output video not found")

    return FileResponse(
        path=job.output_path,
        media_type="video/mp4",
        filename=f"dubbed_{job_id}.mp4",
    )


@app.get("/api/v1/jobs/{job_id}/transcript", tags=["Jobs"])
async def get_transcript(job_id: str):
    """Get the transcript and translation for a job."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": job_id,
        "transcript": job.transcript,
        "translation": job.translation,
        "speakers": job.speakers_detected,
    }


@app.delete("/api/v1/jobs/{job_id}", tags=["Jobs"])
async def delete_job(job_id: str):
    """Delete a job and its associated files."""
    success = await job_manager.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {"message": f"Job {job_id} deleted successfully"}


@app.get("/api/v1/languages", tags=["Info"])
async def list_supported_languages():
    """List supported languages for dubbing."""
    return {
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"},
            {"code": "it", "name": "Italian"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ko", "name": "Korean"},
            {"code": "ar", "name": "Arabic"},
            {"code": "hi", "name": "Hindi"},
            {"code": "ru", "name": "Russian"},
        ]
    }
