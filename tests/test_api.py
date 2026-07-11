"""
Automated tests for the Video Dubbing Platform API.
Tests all endpoints, job lifecycle, and error handling.
"""

import asyncio
import io
import json
import time
import pytest
import httpx
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30  # seconds


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def client():
    """Synchronous HTTP client for tests."""
    return httpx.Client(base_url=BASE_URL, timeout=TEST_TIMEOUT)


@pytest.fixture
def async_client():
    """Async HTTP client for tests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TEST_TIMEOUT)


@pytest.fixture
def sample_video_bytes():
    """Minimal valid MP4 bytes for testing (generated via ffmpeg)."""
    # This is a minimal valid MP4 file header
    # In real tests, use an actual test video file
    return b"\x00\x00\x00\x20\x66\x74\x79\x70\x69\x73\x6f\x6d" + b"\x00" * 100


@pytest.fixture
def sample_video_file(tmp_path):
    """Create a test video file using ffmpeg if available."""
    video_path = tmp_path / "test_video.mp4"
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffmpeg", "-f", "lavfi",
                "-i", "testsrc=duration=5:size=320x240:rate=24",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=5",
                "-c:v", "libx264", "-c:a", "aac",
                "-t", "5", "-y", str(video_path),
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and video_path.exists():
            return video_path
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# Health Check Tests
# ─────────────────────────────────────────────

class TestHealthCheck:
    def test_health_endpoint_returns_200(self, client):
        """Health check should return 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client):
        """Health response should have required fields."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "version" in data
        assert "service" in data

    def test_health_service_name(self, client):
        """Service name should be video-dubbing-platform."""
        response = client.get("/health")
        data = response.json()
        assert data["service"] == "video-dubbing-platform"


# ─────────────────────────────────────────────
# Languages Endpoint Tests
# ─────────────────────────────────────────────

class TestLanguagesEndpoint:
    def test_languages_endpoint_returns_200(self, client):
        """Languages endpoint should return 200."""
        response = client.get("/api/v1/languages")
        assert response.status_code == 200

    def test_languages_response_has_list(self, client):
        """Languages response should contain a list."""
        response = client.get("/api/v1/languages")
        data = response.json()
        assert "languages" in data
        assert isinstance(data["languages"], list)
        assert len(data["languages"]) >= 5

    def test_languages_have_required_fields(self, client):
        """Each language should have code and name."""
        response = client.get("/api/v1/languages")
        languages = response.json()["languages"]
        for lang in languages:
            assert "code" in lang
            assert "name" in lang

    def test_english_is_supported(self, client):
        """English should be in supported languages."""
        response = client.get("/api/v1/languages")
        codes = [l["code"] for l in response.json()["languages"]]
        assert "en" in codes

    def test_spanish_is_supported(self, client):
        """Spanish should be in supported languages."""
        response = client.get("/api/v1/languages")
        codes = [l["code"] for l in response.json()["languages"]]
        assert "es" in codes


# ─────────────────────────────────────────────
# Job Management Tests
# ─────────────────────────────────────────────

class TestJobManagement:
    def test_list_jobs_returns_200(self, client):
        """Job list endpoint should return 200."""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200

    def test_list_jobs_response_structure(self, client):
        """Job list should have jobs array and total."""
        response = client.get("/api/v1/jobs")
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert isinstance(data["jobs"], list)

    def test_get_nonexistent_job_returns_404(self, client):
        """Getting a nonexistent job should return 404."""
        response = client.get("/api/v1/jobs/nonexistent-job-id")
        assert response.status_code == 404

    def test_delete_nonexistent_job_returns_404(self, client):
        """Deleting a nonexistent job should return 404."""
        response = client.delete("/api/v1/jobs/nonexistent-job-id")
        assert response.status_code == 404

    def test_download_nonexistent_job_returns_404(self, client):
        """Downloading from nonexistent job should return 404."""
        response = client.get("/api/v1/jobs/nonexistent-job-id/download")
        assert response.status_code == 404


# ─────────────────────────────────────────────
# Job Creation Tests
# ─────────────────────────────────────────────

class TestJobCreation:
    def test_create_job_with_non_video_returns_400(self, client):
        """Non-video file should be rejected with 400."""
        response = client.post(
            "/api/v1/jobs",
            files={"video": ("test.txt", b"not a video", "text/plain")},
            params={"target_language": "es"},
        )
        assert response.status_code == 400

    def test_create_job_with_valid_video(self, client, sample_video_file):
        """Valid video file should create a job."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        with open(sample_video_file, "rb") as f:
            response = client.post(
                "/api/v1/jobs",
                files={"video": ("test.mp4", f, "video/mp4")},
                params={
                    "source_language": "en",
                    "target_language": "es",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ["pending", "extracting_audio", "transcribing"]
        return data["job_id"]

    def test_create_job_response_has_required_fields(self, client, sample_video_file):
        """Created job response should have all required fields."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        with open(sample_video_file, "rb") as f:
            response = client.post(
                "/api/v1/jobs",
                files={"video": ("test.mp4", f, "video/mp4")},
                params={"target_language": "fr"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert "message" in data
        assert "source_language" in data
        assert "target_language" in data
        assert "created_at" in data

    def test_create_job_with_different_languages(self, client, sample_video_file):
        """Should accept different target languages."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        for lang in ["es", "fr", "de", "ja"]:
            with open(sample_video_file, "rb") as f:
                response = client.post(
                    "/api/v1/jobs",
                    files={"video": ("test.mp4", f, "video/mp4")},
                    params={"target_language": lang},
                )
            assert response.status_code == 200, f"Failed for language: {lang}"


# ─────────────────────────────────────────────
# Job Status Tests
# ─────────────────────────────────────────────

class TestJobStatus:
    def test_job_status_after_creation(self, client, sample_video_file):
        """Job status should be retrievable after creation."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        # Create job
        with open(sample_video_file, "rb") as f:
            create_response = client.post(
                "/api/v1/jobs",
                files={"video": ("test.mp4", f, "video/mp4")},
                params={"target_language": "es"},
            )
        job_id = create_response.json()["job_id"]

        # Get status
        status_response = client.get(f"/api/v1/jobs/{job_id}")
        assert status_response.status_code == 200

        data = status_response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "progress" in data
        assert 0 <= data["progress"] <= 100

    def test_job_status_has_valid_status_values(self, client, sample_video_file):
        """Job status should be one of the valid enum values."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        valid_statuses = {
            "pending", "extracting_audio", "transcribing", "diarizing",
            "translating", "synthesizing", "mixing", "completed", "failed",
        }

        with open(sample_video_file, "rb") as f:
            create_response = client.post(
                "/api/v1/jobs",
                files={"video": ("test.mp4", f, "video/mp4")},
                params={"target_language": "es"},
            )
        job_id = create_response.json()["job_id"]

        status_response = client.get(f"/api/v1/jobs/{job_id}")
        data = status_response.json()
        assert data["status"] in valid_statuses


# ─────────────────────────────────────────────
# Download Tests
# ─────────────────────────────────────────────

class TestDownload:
    def test_download_pending_job_returns_400(self, client, sample_video_file):
        """Downloading from a pending job should return 400."""
        if sample_video_file is None:
            pytest.skip("ffmpeg not available to generate test video")

        with open(sample_video_file, "rb") as f:
            create_response = client.post(
                "/api/v1/jobs",
                files={"video": ("test.mp4", f, "video/mp4")},
                params={"target_language": "es"},
            )
        job_id = create_response.json()["job_id"]

        # Immediately try to download (job won't be complete)
        # Unless the test video processes extremely fast
        status = client.get(f"/api/v1/jobs/{job_id}").json()["status"]
        if status != "completed":
            response = client.get(f"/api/v1/jobs/{job_id}/download")
            assert response.status_code == 400


# ─────────────────────────────────────────────
# Unit Tests (mocked)
# ─────────────────────────────────────────────

class TestPipelineUnits:
    """Unit tests with mocked external dependencies."""

    def test_language_code_validation(self):
        """Language codes should be validated."""
        from app.models.schemas import LanguageCode
        assert LanguageCode.ENGLISH == "en"
        assert LanguageCode.SPANISH == "es"
        assert LanguageCode.AUTO == "auto"

    def test_job_status_enum(self):
        """Job status enum should have all expected values."""
        from app.models.schemas import JobStatus
        assert JobStatus.PENDING == "pending"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"

    def test_dubbing_job_creation(self):
        """DubbingJob should initialize correctly."""
        from app.models.job import DubbingJob
        from app.models.schemas import LanguageCode, JobStatus

        job = DubbingJob(
            job_id="test-123",
            video_path="/tmp/test.mp4",
            source_language=LanguageCode.ENGLISH,
            target_language=LanguageCode.SPANISH,
        )

        assert job.job_id == "test-123"
        assert job.status == JobStatus.PENDING
        assert job.progress == 0.0
        assert job.error is None

    def test_dubbing_job_update_status(self):
        """Job status update should reflect in fields."""
        from app.models.job import DubbingJob
        from app.models.schemas import LanguageCode, JobStatus

        job = DubbingJob(
            job_id="test-456",
            video_path="/tmp/test.mp4",
            source_language=LanguageCode.ENGLISH,
            target_language=LanguageCode.FRENCH,
        )

        job.update_status(JobStatus.TRANSCRIBING, 25.0, "Transcribing audio")
        assert job.status == JobStatus.TRANSCRIBING
        assert job.progress == 25.0
        assert job.current_stage == "Transcribing audio"

    def test_dubbing_job_mark_failed(self):
        """Marking job as failed should set error."""
        from app.models.job import DubbingJob
        from app.models.schemas import LanguageCode, JobStatus

        job = DubbingJob(
            job_id="test-789",
            video_path="/tmp/test.mp4",
            source_language=LanguageCode.AUTO,
            target_language=LanguageCode.GERMAN,
        )

        job.mark_failed("ffmpeg error: file not found")
        assert job.status == JobStatus.FAILED
        assert "ffmpeg error" in job.error

    def test_tts_speed_estimation(self):
        """TTS speed should be clamped to valid range."""
        from app.services.tts_synthesizer import TTSSynthesizer

        synthesizer = TTSSynthesizer.__new__(TTSSynthesizer)

        # Normal speed
        speed = synthesizer._estimate_speed("Hello world", 2.0)
        assert 0.5 <= speed <= 2.5

        # Very fast speech needed
        speed = synthesizer._estimate_speed("This is a very long sentence with many words that needs to fit quickly", 1.0)
        assert speed <= 2.5

        # Very slow speech
        speed = synthesizer._estimate_speed("Hi", 10.0)
        assert speed >= 0.5

    def test_raw_segment_creation(self):
        """RawSegment should store text and timing."""
        from app.services.transcriber import RawSegment

        seg = RawSegment(text="Hello world", start=1.5, end=3.2)
        assert seg.text == "Hello world"
        assert seg.start == 1.5
        assert seg.end == 3.2

    def test_speaker_segment_schema(self):
        """SpeakerSegment schema should serialize correctly."""
        from app.models.schemas import SpeakerSegment

        seg = SpeakerSegment(
            speaker_id="SPEAKER_1",
            start_time=0.0,
            end_time=5.0,
            original_text="Hello",
            translated_text="Hola",
            voice_assigned="alloy",
        )

        data = seg.model_dump()
        assert data["speaker_id"] == "SPEAKER_1"
        assert data["translated_text"] == "Hola"


# ─────────────────────────────────────────────
# Integration Test (end-to-end with mocks)
# ─────────────────────────────────────────────

class TestIntegration:
    """Integration tests using mocked OpenAI/ffmpeg."""

    @pytest.mark.asyncio
    async def test_pipeline_stages_called_in_order(self, tmp_path):
        """Pipeline should call stages in correct order."""
        from app.services.pipeline import DubbingPipeline
        from app.models.job import DubbingJob
        from app.models.schemas import LanguageCode

        stages = []

        class MockExtractor:
            async def extract(self, *args, **kwargs):
                stages.append("extract")
                return tmp_path / "audio.wav"

        class MockTranscriber:
            async def transcribe(self, *args, **kwargs):
                stages.append("transcribe")
                from app.services.transcriber import RawSegment
                return [RawSegment("Hello", 0.0, 1.0)]

        class MockDiarizer:
            async def diarize(self, *args, **kwargs):
                stages.append("diarize")
                from app.models.schemas import SpeakerSegment, SpeakerInfo
                seg = SpeakerSegment(
                    speaker_id="SPEAKER_1",
                    start_time=0.0,
                    end_time=1.0,
                    original_text="Hello",
                    translated_text="",
                    voice_assigned="alloy",
                )
                info = SpeakerInfo(
                    speaker_id="SPEAKER_1",
                    voice_assigned="alloy",
                    segment_count=1,
                    total_duration=1.0,
                )
                return [seg], [info]

        class MockTranslator:
            async def translate(self, segments, **kwargs):
                stages.append("translate")
                return segments

        class MockTTS:
            async def synthesize_all(self, *args, **kwargs):
                stages.append("synthesize")
                return []

        class MockMixer:
            async def mix(self, *args, **kwargs):
                stages.append("mix")
                out = tmp_path / "output.mp4"
                out.touch()
                return out

        pipeline = DubbingPipeline.__new__(DubbingPipeline)
        pipeline.audio_extractor = MockExtractor()
        pipeline.transcriber = MockTranscriber()
        pipeline.diarizer = MockDiarizer()
        pipeline.translator = MockTranslator()
        pipeline.tts = MockTTS()
        pipeline.mixer = MockMixer()

        # Create dummy audio file for transcriber
        (tmp_path / "audio.wav").touch()

        job = DubbingJob(
            job_id="test-integration",
            video_path=str(tmp_path / "video.mp4"),
            source_language=LanguageCode.ENGLISH,
            target_language=LanguageCode.SPANISH,
        )
        (tmp_path / "video.mp4").touch()

        result = await pipeline.run(job)
        assert result.exists()
        assert stages == ["extract", "transcribe", "diarize", "translate", "synthesize", "mix"]


# ─────────────────────────────────────────────
# Run tests
# ─────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
