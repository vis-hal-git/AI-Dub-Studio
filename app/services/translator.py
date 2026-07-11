"""
Translation service using LangChain + GPT-4o.
Translates transcript segments while preserving speaker identity and conversation flow.
"""

import json
import asyncio
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import SystemMessage, HumanMessage

from app.models.schemas import SpeakerSegment, LanguageCode
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

LANGUAGE_NAMES = {
    "auto": "detected",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese (Mandarin)",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "ru": "Russian",
}

TRANSLATION_SYSTEM_PROMPT = """You are a professional translator and dubbing specialist.
Your task is to translate dialogue from {source_lang} to {target_lang} for video dubbing.

Translation guidelines for dubbing:
1. ACCURACY: Preserve the original meaning precisely
2. NATURAL SPEECH: Translations should sound natural when spoken aloud
3. TIMING AWARENESS: Keep translations roughly the same length as originals (for lip sync)
4. SPEAKER CONSISTENCY: Each speaker should have a consistent voice/style
5. CONTEXT: Consider the conversation flow — responses should make sense given prior context
6. REGISTER: Match the formality level of the original speaker
7. IDIOMS: Adapt idioms to equivalent expressions in the target language

Return ONLY valid JSON:
{{
  "translations": [
    {{
      "index": 0,
      "speaker_id": "SPEAKER_1",
      "translated_text": "...",
      "timing_note": "slightly condensed for sync"
    }}
  ]
}}"""

TRANSLATION_USER_PROMPT = """Translate these dialogue segments from {source_lang} to {target_lang}.

Segments to translate:
{segments_json}

Provide natural-sounding dubbing translations."""


class Translator:
    """Translates dialogue segments using LangChain + GPT-4o."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.GPT_MODEL,
            temperature=0.3,
            api_key=settings.OPENAI_API_KEY,
        )

    async def translate(
        self,
        segments: List[SpeakerSegment],
        source_language: LanguageCode,
        target_language: LanguageCode,
    ) -> List[SpeakerSegment]:
        """
        Translate all segments while preserving speaker identity.
        """
        if not segments:
            return []

        source_name = LANGUAGE_NAMES.get(source_language.value, source_language.value)
        target_name = LANGUAGE_NAMES.get(target_language.value, target_language.value)

        logger.info(f"Translating {len(segments)} segments: {source_name} → {target_name}")

        # Batch translate for efficiency and context awareness
        batch_size = 30
        translated_map = {}

        tasks = []
        for i in range(0, len(segments), batch_size):
            batch = segments[i : i + batch_size]
            tasks.append(
                self._translate_batch(batch, i, source_name, target_name)
            )

        # Run batches with limited concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Translation batch failed: {result}")
            elif result:
                translated_map.update(result)

        # Apply translations to segments
        translated_segments = []
        for i, seg in enumerate(segments):
            translated_text = translated_map.get(i, seg.original_text)
            translated_segments.append(
                SpeakerSegment(
                    speaker_id=seg.speaker_id,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    original_text=seg.original_text,
                    translated_text=translated_text,
                    voice_assigned=seg.voice_assigned,
                )
            )

        logger.info(f"Translation complete: {len(translated_segments)} segments")
        return translated_segments

    async def _translate_batch(
        self,
        batch: List[SpeakerSegment],
        offset: int,
        source_name: str,
        target_name: str,
    ) -> dict:
        """Translate a batch of segments using LangChain."""
        segments_data = [
            {
                "index": i + offset,
                "speaker_id": seg.speaker_id,
                "start": seg.start_time,
                "end": seg.end_time,
                "duration": round(seg.end_time - seg.start_time, 2),
                "text": seg.original_text,
            }
            for i, seg in enumerate(batch)
        ]

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=TRANSLATION_SYSTEM_PROMPT.format(
                source_lang=source_name,
                target_lang=target_name,
            )),
            HumanMessage(content=TRANSLATION_USER_PROMPT.format(
                source_lang=source_name,
                target_lang=target_name,
                segments_json=json.dumps(segments_data, indent=2, ensure_ascii=False),
            )),
        ])

        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = await chain.ainvoke({})
            translation_map = {}

            for item in result.get("translations", []):
                idx = item.get("index", 0)
                text = item.get("translated_text", "")
                if text:
                    translation_map[idx] = text

            return translation_map

        except Exception as e:
            logger.error(f"Translation batch failed: {e}")
            # Fallback: return original text
            return {(i + offset): seg.original_text for i, seg in enumerate(batch)}
