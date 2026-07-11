import asyncio
from app.services.tts_synthesizer import TTSSynthesizer
from app.models.schemas import SpeakerSegment, SpeakerInfo
from app.core.config import settings

async def main():
    print("Initializing...")
    tts = TTSSynthesizer()
    print("Synthesizing...")
    try:
        segments = [
            SpeakerSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=2.0,
                original_text="Hello",
                translated_text="Hola"
            )
        ]
        speaker_infos = [
            SpeakerInfo(speaker_id="speaker_0", voice_assigned="alloy")
        ]
        result = await tts.synthesize_all(segments, speaker_infos, "test_job")
        print("Success:", result)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
