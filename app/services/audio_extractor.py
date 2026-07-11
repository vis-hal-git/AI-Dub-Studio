"""Audio extraction from video using ffmpeg."""

import asyncio
import subprocess
from pathlib import Path

from app.core.subprocess import run_async_subprocess
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AudioExtractor:
    """Extracts audio from video files using ffmpeg."""

    async def extract(self, video_path: str, job_id: str) -> Path:
        """
        Extract audio from video file.
        
        Returns mono 16kHz WAV (optimal for Whisper transcription).
        """
        audio_path = settings.TEMP_DIR / f"{job_id}_audio.wav"

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",                    # No video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",           # 16kHz sample rate (Whisper optimal)
            "-ac", "1",               # Mono
            "-y",                     # Overwrite output
            str(audio_path),
        ]

        logger.info(f"[{job_id}] Extracting audio: {' '.join(cmd)}")

        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio extraction failed (code {proc.returncode}): "
                f"{stderr.decode()}"
            )

        if not audio_path.exists():
            raise RuntimeError("Audio file was not created by ffmpeg")

        size_mb = audio_path.stat().st_size / 1024 / 1024
        logger.info(f"[{job_id}] Audio extracted: {audio_path} ({size_mb:.1f}MB)")

        # Check video duration
        duration = await self._get_duration(video_path)
        if duration > settings.MAX_VIDEO_DURATION:
            raise ValueError(
                f"Video duration {duration:.1f}s exceeds maximum "
                f"{settings.MAX_VIDEO_DURATION}s (10 minutes)"
            )

        return audio_path

    async def _get_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"Could not get video duration: {stderr.decode()}")
            return 0.0

        try:
            return float(stdout.decode().strip())
        except ValueError:
            return 0.0

    async def extract_segment(
        self, audio_path: str, start: float, end: float, output_path: Path
    ) -> Path:
        """Extract a specific time segment from audio."""
        duration = end - start
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-ss", str(start),
            "-t", str(duration),
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            str(output_path),
        ]

        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return output_path
