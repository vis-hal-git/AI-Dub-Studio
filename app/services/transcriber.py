"""
Speech transcription using OpenAI Whisper API.
Handles chunking for long audio files.
"""

import asyncio
import io
from pathlib import Path
from typing import List, Dict, Any, Optional

import openai

from app.models.schemas import LanguageCode
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Whisper API limit: 25MB per request
WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24MB to be safe
CHUNK_SECONDS = 120  # 2-minute chunks for long audio


class RawSegment:
    """Raw transcription segment from Whisper."""

    def __init__(
        self,
        text: str,
        start: float,
        end: float,
        words: Optional[List[Dict]] = None,
    ):
        self.text = text.strip()
        self.start = start
        self.end = end
        self.words = words or []

    def __repr__(self):
        return f"RawSegment({self.start:.1f}-{self.end:.1f}: {self.text[:50]})"


class Transcriber:
    """Transcribes audio using OpenAI Whisper with chunking support."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def transcribe(
        self,
        audio_path: Path,
        source_language: LanguageCode = LanguageCode.AUTO,
    ) -> List[RawSegment]:
        """
        Transcribe audio file using Whisper.
        Automatically chunks large files.
        """
        file_size = audio_path.stat().st_size

        if file_size > WHISPER_MAX_BYTES:
            logger.info(f"Large audio file ({file_size / 1024 / 1024:.1f}MB), chunking...")
            return await self._transcribe_chunked(audio_path, source_language)
        else:
            return await self._transcribe_single(audio_path, source_language)

    async def _transcribe_single(
        self, audio_path: Path, source_language: LanguageCode
    ) -> List[RawSegment]:
        """Transcribe a single audio file."""
        lang = None if source_language == LanguageCode.AUTO else source_language.value

        with open(audio_path, "rb") as f:
            response = await self.client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=f,
                language=lang,
                response_format="verbose_json",
                timestamp_granularities=["segment", "word"],
            )

        return self._parse_whisper_response(response)

    async def _transcribe_chunked(
        self, audio_path: Path, source_language: LanguageCode
    ) -> List[RawSegment]:
        """Transcribe a large audio file in chunks using ffmpeg."""
        import subprocess
        import tempfile

        # Get total duration
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        total_duration = float(stdout.decode().strip() or "0")

        all_segments = []
        offset = 0.0

        while offset < total_duration:
            chunk_path = audio_path.parent / f"{audio_path.stem}_chunk_{int(offset)}.wav"

            # Extract chunk
            extract_proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(audio_path),
                "-ss", str(offset),
                "-t", str(CHUNK_SECONDS),
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                "-y", str(chunk_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await extract_proc.communicate()

            if chunk_path.exists():
                segments = await self._transcribe_single(chunk_path, source_language)

                # Adjust timestamps by offset
                for seg in segments:
                    seg.start += offset
                    seg.end += offset

                all_segments.extend(segments)
                chunk_path.unlink(missing_ok=True)

            offset += CHUNK_SECONDS

        return all_segments

    def _parse_whisper_response(self, response) -> List[RawSegment]:
        """Parse Whisper API verbose_json response into RawSegments."""
        segments = []

        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                words = []
                if hasattr(seg, "words") and seg.words:
                    words = [
                        {"word": w.word, "start": w.start, "end": w.end}
                        for w in seg.words
                    ]

                segments.append(
                    RawSegment(
                        text=seg.text,
                        start=seg.start,
                        end=seg.end,
                        words=words,
                    )
                )
        elif hasattr(response, "text"):
            # Fallback: single segment with full text
            segments.append(
                RawSegment(text=response.text, start=0.0, end=0.0)
            )

        return segments
