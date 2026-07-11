"""Application configuration."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Directories
    BASE_DIR: Path = Path("/tmp/video-dubbing")
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    OUTPUT_DIR: Path = BASE_DIR / "outputs"
    TEMP_DIR: Path = BASE_DIR / "temp"

    # OpenAI Models
    WHISPER_MODEL: str = "whisper-1"
    GPT_MODEL: str = "gpt-4o"
    TTS_MODEL: str = "tts-1"

    # Processing limits
    MAX_VIDEO_DURATION: int = 600  # 10 minutes in seconds
    MAX_FILE_SIZE_MB: int = 500
    CHUNK_DURATION: int = 30  # seconds per audio chunk for processing

    # TTS voices (OpenAI voices for different speakers)
    TTS_VOICES: list = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    # Speaker diarization
    MIN_SPEAKERS: int = 1
    MAX_SPEAKERS: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
