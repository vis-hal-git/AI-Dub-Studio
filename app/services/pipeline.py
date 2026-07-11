"""
Core dubbing pipeline using LangChain + OpenAI.
Orchestrates: audio extraction → transcription → diarization → translation → TTS → mixing
"""

import asyncio
import json
from pathlib import Path
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from app.models.job import DubbingJob
from app.models.schemas import JobStatus, SpeakerSegment, SpeakerInfo
from app.services.audio_extractor import AudioExtractor
from app.services.transcriber import Transcriber
from app.services.diarizer import SpeakerDiarizer
from app.services.translator import Translator
from app.services.tts_synthesizer import TTSSynthesizer
from app.services.video_mixer import VideoMixer
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DubbingPipeline:
    """Orchestrates the full video dubbing pipeline."""

    def __init__(self):
        self.audio_extractor = AudioExtractor()
        self.transcriber = Transcriber()
        self.diarizer = SpeakerDiarizer()
        self.translator = Translator()
        self.tts = TTSSynthesizer()
        self.mixer = VideoMixer()

    async def run(self, job: DubbingJob) -> Path:
        """Run the full dubbing pipeline for a job."""

        # Stage 1: Extract audio
        job.update_status(JobStatus.EXTRACTING_AUDIO, 5, "Extracting audio from video")
        audio_path = await self.audio_extractor.extract(job.video_path, job.job_id)
        logger.info(f"[{job.job_id}] Audio extracted: {audio_path}")

        # Stage 2: Transcribe with Whisper
        job.update_status(JobStatus.TRANSCRIBING, 20, "Transcribing speech with Whisper")
        raw_segments = await self.transcriber.transcribe(
            audio_path,
            source_language=job.source_language,
        )
        logger.info(f"[{job.job_id}] Transcribed {len(raw_segments)} segments")

        # Stage 3: Speaker diarization via LangChain
        job.update_status(JobStatus.DIARIZING, 40, "Identifying speakers")
        diarized_segments, speaker_infos = await self.diarizer.diarize(
            audio_path=audio_path,
            raw_segments=raw_segments,
            job_id=job.job_id,
        )
        job.speakers_detected = speaker_infos
        job.transcript = diarized_segments
        logger.info(f"[{job.job_id}] Detected {len(speaker_infos)} speakers")

        # Stage 4: Translate via LangChain + GPT-4o
        job.update_status(JobStatus.TRANSLATING, 55, "Translating dialogue")
        translated_segments = await self.translator.translate(
            segments=diarized_segments,
            source_language=job.source_language,
            target_language=job.target_language,
        )
        job.translation = translated_segments
        logger.info(f"[{job.job_id}] Translation complete")

        # Stage 5: Text-to-speech synthesis
        job.update_status(JobStatus.SYNTHESIZING, 70, "Synthesizing dubbed voices")
        audio_segments = await self.tts.synthesize_all(
            segments=translated_segments,
            speaker_infos=speaker_infos,
            job_id=job.job_id,
        )
        logger.info(f"[{job.job_id}] Synthesized {len(audio_segments)} audio segments")

        # Stage 6: Mix dubbed audio with video
        job.update_status(JobStatus.MIXING, 85, "Mixing audio with video")
        output_path = await self.mixer.mix(
            video_path=job.video_path,
            audio_segments=audio_segments,
            original_audio_path=audio_path,
            preserve_background=job.preserve_background_audio,
            job_id=job.job_id,
        )
        logger.info(f"[{job.job_id}] Video mixed: {output_path}")

        return output_path
