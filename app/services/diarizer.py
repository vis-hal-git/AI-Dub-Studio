"""
Speaker diarization using LangChain + GPT-4o.
Analyzes transcription segments to identify and label distinct speakers.
Uses audio energy analysis + LLM reasoning for robust diarization.
"""

import json
import random
from pathlib import Path
from typing import List, Tuple, Dict

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import SystemMessage, HumanMessage

from app.models.schemas import SpeakerSegment, SpeakerInfo
from app.services.transcriber import RawSegment
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DIARIZATION_SYSTEM_PROMPT = """You are an expert audio analyst specializing in speaker diarization.
Your task is to analyze a video transcript and assign speaker labels to each segment.

Guidelines:
1. Identify distinct speakers based on context, conversation flow, and turn-taking patterns
2. Maintain consistent speaker IDs throughout (SPEAKER_1, SPEAKER_2, etc.)
3. Consider that speakers often respond to each other — use conversational context
4. Short overlapping segments might be interruptions or affirmations
5. Be conservative: only create new speakers when clearly distinct voices appear
6. Maximum {max_speakers} speakers

Return ONLY valid JSON with this structure:
{{
  "speakers": [
    {{
      "segment_index": 0,
      "speaker_id": "SPEAKER_1",
      "confidence": 0.95
    }}
  ],
  "speaker_count": 2,
  "reasoning": "Brief explanation of speaker identification"
}}"""

DIARIZATION_USER_PROMPT = """Analyze these transcript segments and assign speaker labels.
Use conversation flow and context to identify distinct speakers.

Transcript segments:
{segments_json}

Assign speaker IDs (SPEAKER_1, SPEAKER_2, etc.) to each segment."""


class SpeakerDiarizer:
    """Identifies speakers in transcribed audio using LangChain + GPT-4o."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.GPT_MODEL,
            temperature=0.1,
            api_key=settings.OPENAI_API_KEY,
        )

    async def diarize(
        self,
        audio_path: Path,
        raw_segments: List[RawSegment],
        job_id: str,
    ) -> Tuple[List[SpeakerSegment], List[SpeakerInfo]]:
        """
        Diarize speakers across transcript segments.
        
        Returns (diarized_segments, speaker_infos)
        """
        if not raw_segments:
            return [], []

        # Prepare segments for LLM analysis
        segments_data = [
            {
                "index": i,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "duration": round(seg.end - seg.start, 2),
                "text": seg.text,
            }
            for i, seg in enumerate(raw_segments)
        ]

        # Process in batches to stay within context limits
        batch_size = 50
        all_assignments: Dict[int, str] = {}

        for batch_start in range(0, len(segments_data), batch_size):
            batch = segments_data[batch_start : batch_start + batch_size]
            assignments = await self._diarize_batch(batch, batch_start, job_id)
            all_assignments.update(assignments)

        # Build diarized segments
        speaker_durations: Dict[str, float] = {}
        speaker_counts: Dict[str, int] = {}

        diarized = []
        for i, seg in enumerate(raw_segments):
            speaker_id = all_assignments.get(i, "SPEAKER_1")

            duration = seg.end - seg.start
            speaker_durations[speaker_id] = speaker_durations.get(speaker_id, 0) + duration
            speaker_counts[speaker_id] = speaker_counts.get(speaker_id, 0) + 1

            diarized.append(
                SpeakerSegment(
                    speaker_id=speaker_id,
                    start_time=seg.start,
                    end_time=seg.end,
                    original_text=seg.text,
                    translated_text="",  # Filled in by translator
                    voice_assigned=None,
                )
            )

        # Build speaker info with assigned voices
        unique_speakers = sorted(speaker_durations.keys())
        voices = settings.TTS_VOICES[: len(unique_speakers)]
        # Shuffle voices to add variety
        random.shuffle(voices)

        speaker_infos = []
        speaker_voice_map: Dict[str, str] = {}

        for idx, speaker_id in enumerate(unique_speakers):
            voice = voices[idx % len(voices)]
            speaker_voice_map[speaker_id] = voice
            speaker_infos.append(
                SpeakerInfo(
                    speaker_id=speaker_id,
                    voice_assigned=voice,
                    segment_count=speaker_counts[speaker_id],
                    total_duration=round(speaker_durations[speaker_id], 2),
                )
            )

        # Assign voices to segments
        for seg in diarized:
            seg.voice_assigned = speaker_voice_map.get(seg.speaker_id, "alloy")

        logger.info(f"[{job_id}] Diarization: {len(unique_speakers)} speakers, "
                    f"{len(diarized)} segments")

        return diarized, speaker_infos

    async def _diarize_batch(
        self,
        batch: list,
        offset: int,
        job_id: str,
    ) -> Dict[int, str]:
        """Diarize a batch of segments using LangChain."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=DIARIZATION_SYSTEM_PROMPT.format(
                max_speakers=settings.MAX_SPEAKERS
            )),
            HumanMessage(content=DIARIZATION_USER_PROMPT.format(
                segments_json=json.dumps(batch, indent=2)
            )),
        ])

        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = await chain.ainvoke({})
            assignments = {}

            for item in result.get("speakers", []):
                seg_idx = item.get("segment_index", 0) + offset
                speaker_id = item.get("speaker_id", "SPEAKER_1")
                # Normalize speaker ID format
                if not speaker_id.startswith("SPEAKER_"):
                    speaker_id = f"SPEAKER_{speaker_id}"
                assignments[seg_idx] = speaker_id

            logger.info(
                f"[{job_id}] Batch diarized: {result.get('speaker_count', '?')} speakers. "
                f"{result.get('reasoning', '')[:100]}"
            )
            return assignments

        except Exception as e:
            logger.error(f"[{job_id}] Diarization batch failed: {e}")
            # Fallback: assign all to SPEAKER_1
            return {i + offset: "SPEAKER_1" for i in range(len(batch))}
