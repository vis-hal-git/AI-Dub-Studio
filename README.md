# 🎬 Video Dubbing Platform

> LLM/AI Engineering Assignment 3 — Multi-speaker video translation and dubbing using LangChain + OpenAI

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Frontend (UI)                        │
│             Vanilla HTML / CSS / JavaScript                 │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP Requests
┌─────────────────────────▼───────────────────────────────────┐
│                     FastAPI REST API                        │
│  POST /api/v1/jobs   GET /api/v1/jobs/{id}   GET /download  │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────▼──────────────────┐
          │        Dubbing Pipeline          │
          │                                  │
          │  1. AudioExtractor (ffmpeg)      │
          │     └─ Extract WAV from MP4      │
          │                                  │
          │  2. Transcriber (Whisper API)    │
          │     └─ Speech → timestamped text │
          │                                  │
          │  3. SpeakerDiarizer (LangChain)  │
          │     └─ GPT-4o identifies speakers│
          │                                  │
          │  4. Translator (LangChain)       │
          │     └─ GPT-4o translates dialogue│
          │                                  │
          │  5. TTSSynthesizer (OpenAI TTS)  │
          │     └─ Per-speaker voice synthesis│
          │                                  │
          │  6. VideoMixer (ffmpeg)          │
          │     └─ Sync audio + mux to MP4   │
          └──────────────────────────────────┘
```

## Features

| Requirement | Implementation |
|---|---|
| User-Friendly Web Interface | Responsive frontend to upload videos, track progress, and download results |
| Videos up to 10 minutes | Duration validation via ffprobe; chunked Whisper transcription for large files |
| Multiple speaker identification | LangChain + GPT-4o diarization using conversation context |
| Accurate transcripts & translations | OpenAI Whisper + GPT-4o with dubbing-specific prompts |
| Natural-sounding dubbed voices | OpenAI TTS with 6 distinct voices, one per speaker |
| Audio/video synchronization | Speed-adjusted TTS + ffmpeg adelay filter placement |
| Processing status APIs | `/api/v1/jobs/{id}` with progress, stage, and speaker data |
| Downloadable output | `/api/v1/jobs/{id}/download` returns dubbed MP4 |
| Docker deployment | Multi-container setup via `docker-compose.yml` and optimized `Dockerfile` |
| Automated tests | `pytest` with unit + integration tests |
| LangChain | Used for diarization and translation chains |
| OpenAI API | Whisper (STT), GPT-4o (NLP), TTS (speech synthesis) |

---

## Quick Start

### Option A: Docker (Recommended)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY

# 2. Build and start
docker compose up --build

# 3. Access the platform
# Web Interface (Frontend): http://localhost:3000
# API Documentation: http://localhost:8000/docs
```

### Option B: Local Development

```bash
# Prerequisites: Python 3.11+, ffmpeg

# 1. Install ffmpeg
# macOS:   brew install ffmpeg
# Ubuntu:  apt-get install ffmpeg
# Windows: https://ffmpeg.org/download.html

# 2. Install Python deps
pip install -r requirements.txt

# 3. Configure API key
cp .env.example .env
# Edit .env — add OPENAI_API_KEY

# 4. Start the backend server
./scripts/start_dev.sh
# OR
uvicorn app.main:app --reload

# 5. Start the frontend server (in a new terminal)
python -m http.server 3000 --directory frontend

# 6. Open your browser
# Navigate to http://localhost:3000
```

---

## API Reference

### `POST /api/v1/jobs` — Create dubbing job

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -F "video=@my_video.mp4" \
  -F "source_language=en" \
  -F "target_language=es" \
  -F "preserve_background_audio=true"
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Job created successfully. Processing started.",
  "source_language": "en",
  "target_language": "es",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### `GET /api/v1/jobs/{job_id}` — Check status

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-...
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "translating",
  "progress": 55.0,
  "current_stage": "Translating dialogue",
  "speakers_detected": [
    {
      "speaker_id": "SPEAKER_1",
      "voice_assigned": "alloy",
      "segment_count": 12,
      "total_duration": 45.3
    },
    {
      "speaker_id": "SPEAKER_2",
      "voice_assigned": "nova",
      "segment_count": 8,
      "total_duration": 32.1
    }
  ],
  "transcript": [...],
  "translation": [...]
}
```

**Status values:** `pending → extracting_audio → transcribing → diarizing → translating → synthesizing → mixing → completed`

---

### `GET /api/v1/jobs/{job_id}/download` — Download output

```bash
curl -OJ http://localhost:8000/api/v1/jobs/a1b2c3d4-.../download
# Downloads: dubbed_a1b2c3d4-....mp4
```

---

### `GET /api/v1/jobs/{job_id}/transcript` — Get transcript/translation

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-.../transcript
```

---

### `GET /api/v1/jobs` — List all jobs

```bash
curl http://localhost:8000/api/v1/jobs
```

---

### `DELETE /api/v1/jobs/{job_id}` — Delete job

```bash
curl -X DELETE http://localhost:8000/api/v1/jobs/a1b2c3d4-...
```

---

### `GET /api/v1/languages` — Supported languages

```bash
curl http://localhost:8000/api/v1/languages
```

---

## Supported Languages

| Code | Language |
|---|---|
| `en` | English |
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `it` | Italian |
| `pt` | Portuguese |
| `ja` | Japanese |
| `zh` | Chinese |
| `ko` | Korean |
| `ar` | Arabic |
| `hi` | Hindi |
| `ru` | Russian |

---

## Running Tests

```bash
# Unit tests (no API key needed for most)
./scripts/run_tests.sh

# OR directly with pytest
python -m pytest tests/ -v

# With Docker
docker compose --profile test up tests
```

---

## Pipeline Deep Dive

### 1. Audio Extraction (ffmpeg)
Extracts mono 16kHz WAV from the input video — optimal format for Whisper.

### 2. Transcription (OpenAI Whisper)
- Uses `whisper-1` via the OpenAI API
- Returns word-level timestamps
- Auto-chunks files > 24MB into 2-minute segments
- Auto-detects language if `source_language=auto`

### 3. Speaker Diarization (LangChain + GPT-4o)
- Passes transcript segments to GPT-4o via a LangChain chain
- GPT-4o analyzes turn-taking, context, and conversational patterns
- Returns consistent `SPEAKER_N` labels for each segment
- Processed in batches of 50 segments to stay within context limits
- Each unique speaker is assigned a distinct TTS voice

### 4. Translation (LangChain + GPT-4o)
- Dubbing-aware prompt: preserves meaning, natural speech, timing
- Processes batches of 30 segments with full conversational context
- Concurrent batch processing with rate-limit protection

### 5. TTS Synthesis (OpenAI TTS)
- One OpenAI voice per speaker (alloy, echo, fable, onyx, nova, shimmer)
- Speed-adjusted based on target duration for better lip sync
- Up to 5 concurrent synthesis requests

### 6. Video Mixing (ffmpeg)
- Places each TTS clip at exact timestamp using `adelay` filter
- Original audio optionally ducked to 15% (background ambience)
- Video stream copied without re-encoding for speed
- Output: H.264 MP4 with AAC audio

---

## Project Structure

```
video-dubbing/
├── app/
│   ├── main.py                 # FastAPI app + endpoints
│   ├── core/
│   │   ├── config.py           # Settings (env vars)
│   │   └── logging.py          # Logger factory
│   ├── models/
│   │   ├── schemas.py          # Pydantic API schemas
│   │   └── job.py              # DubbingJob data model
│   └── services/
│       ├── job_manager.py      # Job orchestration
│       ├── pipeline.py         # Pipeline coordinator
│       ├── audio_extractor.py  # ffmpeg audio extraction
│       ├── transcriber.py      # Whisper transcription
│       ├── diarizer.py         # LangChain speaker ID
│       ├── translator.py       # LangChain translation
│       ├── tts_synthesizer.py  # OpenAI TTS
│       └── video_mixer.py      # ffmpeg video mixing
├── frontend/
│   ├── index.html              # Web interface layout
│   ├── script.js               # Frontend API integration
│   └── style.css               # Styling and animations
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   └── test_api.py             # Test suite
├── scripts/
│   ├── start_dev.sh            # Dev server launcher
│   └── run_tests.sh            # Test runner
├── Dockerfile                  # API Container definition
├── docker-compose.yml          # Multi-container orchestration (API + Frontend)
├── .dockerignore               # Excludes large files & venv from Docker image
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```
