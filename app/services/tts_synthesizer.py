"""
Text-to-Speech synthesis using OpenAI TTS API.
Generates dubbed voice audio for each speaker segment.
Handles speed adjustment for synchronization.
"""

import asyncio
import io
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

import openai

from app.models.schemas import SpeakerSegment, SpeakerInfo
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SynthesizedSegment:
    """A synthesized audio segment with timing info."""
    speaker_id: str
    voice: str
    start_time: float
    end_time: float
    original_duration: float
    audio_path: Path
    translated_text: str


class TTSSynthesizer:
    """Synthesizes speech using OpenAI TTS, one voice per speaker."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def synthesize_all(
        self,
        segments: List[SpeakerSegment],
        speaker_infos: List[SpeakerInfo],
        job_id: str,
    ) -> List[SynthesizedSegment]:
        """Synthesize all segments with appropriate voices."""

        # Build speaker → voice map
        voice_map = {si.speaker_id: si.voice_assigned for si in speaker_infos}

        # Filter segments with text
        valid_segments = [s for s in segments if s.translated_text.strip()]

        logger.info(f"[{job_id}] Synthesizing {len(valid_segments)} segments...")

        # Synthesize with limited concurrency to avoid rate limits
        semaphore = asyncio.Semaphore(5)

        async def synthesize_with_semaphore(i, seg):
            async with semaphore:
                return await self._synthesize_segment(seg, voice_map, job_id, i)

        tasks = [
            synthesize_with_semaphore(i, seg)
            for i, seg in enumerate(valid_segments)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        synthesized = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{job_id}] Segment {i} synthesis failed: {result}")
            elif result:
                synthesized.append(result)

        logger.info(f"[{job_id}] Synthesized {len(synthesized)}/{len(valid_segments)} segments")
        return synthesized

    async def _synthesize_segment(
        self,
        segment: SpeakerSegment,
        voice_map: Dict[str, str],
        job_id: str,
        idx: int,
    ) -> SynthesizedSegment:
        """Synthesize a single segment."""
        voice = voice_map.get(segment.speaker_id, "alloy")
        original_duration = segment.end_time - segment.start_time

        # Determine speech speed for rough synchronization
        # We'll adjust more precisely during mixing
        speed = self._estimate_speed(segment.translated_text, original_duration)

        output_path = settings.TEMP_DIR / f"{job_id}_tts_{idx:04d}.mp3"

        try:
            response = await self.client.audio.speech.create(
                model=settings.TTS_MODEL,
                voice=voice,
                input=segment.translated_text,
                speed=speed,
                response_format="mp3",
            )

            # Write audio to file
            audio_bytes = b""
            for chunk in response.iter_bytes():
                audio_bytes += chunk

            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            logger.debug(
                f"[{job_id}] Segment {idx}: [{segment.speaker_id}/{voice}] "
                f"{segment.start_time:.1f}s-{segment.end_time:.1f}s "
                f"→ {len(audio_bytes)/1024:.1f}KB (speed={speed:.2f})"
            )

            return SynthesizedSegment(
                speaker_id=segment.speaker_id,
                voice=voice,
                start_time=segment.start_time,
                end_time=segment.end_time,
                original_duration=original_duration,
                audio_path=output_path,
                translated_text=segment.translated_text,
            )

        except Exception as e:
            logger.error(f"[{job_id}] TTS failed for segment {idx}: {e}")
            raise

    def _estimate_speed(self, text: str, target_duration: float) -> float:
        """
        Estimate TTS speed to fit within the original segment duration.
        OpenAI TTS speed range: 0.25 - 4.0
        Average English speech: ~150 words/min = 2.5 words/sec
        """
        if target_duration <= 0:
            return 1.0

        word_count = len(text.split())
        if word_count == 0:
            return 1.0

        # Estimate time at normal speed (1.0)
        # Average TTS: ~2.5 words/second at speed=1.0
        estimated_seconds = word_count / 2.5
        required_speed = estimated_seconds / target_duration

        # Clamp to OpenAI's valid range with slight padding
        return max(0.5, min(2.5, required_speed))
