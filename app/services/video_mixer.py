"""
Video mixing service using ffmpeg.
Combines dubbed audio segments with the original video.
Handles synchronization, background audio, and final output.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import List

from app.services.tts_synthesizer import SynthesizedSegment
from app.core.config import settings
from app.core.logging import get_logger
from app.core.subprocess import run_async_subprocess

logger = get_logger(__name__)


class VideoMixer:
    """Mixes dubbed audio with original video using ffmpeg."""

    async def mix(
        self,
        video_path: str,
        audio_segments: List[SynthesizedSegment],
        original_audio_path: Path,
        preserve_background: bool,
        job_id: str,
    ) -> Path:
        """
        Mix dubbed audio segments with the original video.
        
        Process:
        1. Build a silent audio track of full video duration
        2. Place each TTS segment at the correct timestamp
        3. Optionally mix with ducked original audio (background sounds)
        4. Mux with original video stream
        """
        output_path = settings.OUTPUT_DIR / f"{job_id}_dubbed.mp4"

        # Get video duration
        duration = await self._get_duration(video_path)
        logger.info(f"[{job_id}] Video duration: {duration:.1f}s, "
                    f"{len(audio_segments)} segments to place")

        if not audio_segments:
            # No dubbed audio — just copy the video
            await self._copy_video(video_path, output_path)
            return output_path

        # Build dubbed audio track
        dubbed_audio_path = settings.TEMP_DIR / f"{job_id}_dubbed_audio.wav"
        await self._build_dubbed_audio_track(
            audio_segments=audio_segments,
            total_duration=duration,
            output_path=dubbed_audio_path,
            job_id=job_id,
        )

        # Mix with original background audio if requested
        if preserve_background:
            mixed_audio_path = settings.TEMP_DIR / f"{job_id}_mixed_audio.wav"
            await self._mix_with_background(
                dubbed_audio=dubbed_audio_path,
                original_audio=original_audio_path,
                output_path=mixed_audio_path,
                job_id=job_id,
            )
            final_audio_path = mixed_audio_path
        else:
            final_audio_path = dubbed_audio_path

        # Mux audio with video
        await self._mux_video_audio(
            video_path=video_path,
            audio_path=final_audio_path,
            output_path=output_path,
            job_id=job_id,
        )

        # Clean up temp files
        self._cleanup([dubbed_audio_path, final_audio_path] + 
                     [seg.audio_path for seg in audio_segments])

        logger.info(f"[{job_id}] Output video: {output_path}")
        return output_path

    async def _build_dubbed_audio_track(
        self,
        audio_segments: List[SynthesizedSegment],
        total_duration: float,
        output_path: Path,
        job_id: str,
    ) -> None:
        """
        Build a full-length dubbed audio track by placing TTS segments at correct times.
        Uses ffmpeg amix with adelay filters.
        """
        # Create silence base track
        silence_path = settings.TEMP_DIR / f"{job_id}_silence.wav"
        await self._create_silence(total_duration, silence_path)

        # Build ffmpeg filter complex to overlay each TTS segment
        # ffmpeg -i silence.wav -i seg0.mp3 -i seg1.mp3 ... -filter_complex "..." output.wav

        inputs = ["-i", str(silence_path)]
        filter_parts = []
        mix_inputs = ["[0:a]"]
        valid_segments = 0

        for idx, seg in enumerate(audio_segments):
            if not seg.audio_path.exists():
                continue

            inputs += ["-i", str(seg.audio_path)]
            input_idx = valid_segments + 1
            delay_ms = int(seg.start_time * 1000)

            # adelay adds silence before the segment to place it at the right time
            filter_parts.append(
                f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[seg{valid_segments}]"
            )
            mix_inputs.append(f"[seg{valid_segments}]")
            valid_segments += 1

        if not filter_parts:
            # No valid segments, use silence
            await self._copy_audio(silence_path, output_path)
            return

        # Mix all tracks at once and boost volume to counteract amix's 1/n scaling
        mix_inputs_str = "".join(mix_inputs)
        n_inputs = valid_segments + 1
        filter_parts.append(
            f"{mix_inputs_str}amix=inputs={n_inputs}:duration=first,volume={n_inputs}[mixout]"
        )
        current_mix = "[mixout]"

        filter_complex = ";".join(filter_parts)

        cmd = (
            ["ffmpeg"]
            + inputs
            + [
                "-filter_complex", filter_complex,
                "-map", current_mix,
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-y",
                str(output_path),
            ]
        )

        await self._run_ffmpeg(cmd, job_id, "build dubbed track")

        if not output_path.exists():
            # Fallback: just use silence
            logger.warning(f"[{job_id}] Dubbed track build failed, using silence")
            await self._copy_audio(silence_path, output_path)

        silence_path.unlink(missing_ok=True)

    async def _mix_with_background(
        self,
        dubbed_audio: Path,
        original_audio: Path,
        output_path: Path,
        job_id: str,
    ) -> None:
        """
        Mix dubbed audio with ducked original audio (background sounds only).
        Original audio is ducked to 15% volume to let dubbed speech through.
        """
        cmd = [
            "ffmpeg",
            "-i", str(dubbed_audio),
            "-i", str(original_audio),
            "-filter_complex",
            # Duck original audio to 15%, mix with dubbed
            "[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first,volume=2[out]",
            "-map", "[out]",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            "-y",
            str(output_path),
        ]

        await self._run_ffmpeg(cmd, job_id, "mix background audio")

    async def _mux_video_audio(
        self,
        video_path: str,
        audio_path: Path,
        output_path: Path,
        job_id: str,
    ) -> None:
        """Combine video stream with dubbed audio into final MP4."""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),     # Original video (for video stream)
            "-i", str(audio_path),      # Dubbed audio
            "-map", "0:v",              # Video from first input
            "-map", "1:a",              # Audio from second input
            "-c:v", "copy",             # Copy video (no re-encoding)
            "-c:a", "aac",              # AAC audio codec
            "-b:a", "192k",
            "-shortest",                # Match shortest stream
            "-y",
            str(output_path),
        ]

        await self._run_ffmpeg(cmd, job_id, "mux video+audio")

    async def _create_silence(self, duration: float, output_path: Path) -> None:
        """Create a silent audio file of specified duration."""
        cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-acodec", "pcm_s16le",
            "-y",
            str(output_path),
        ]
        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def _copy_audio(self, src: Path, dst: Path) -> None:
        """Copy audio file."""
        import shutil
        shutil.copy2(src, dst)

    async def _copy_video(self, video_path: str, output_path: Path) -> None:
        """Copy video without modification."""
        cmd = ["ffmpeg", "-i", str(video_path), "-c", "copy", "-y", str(output_path)]
        await self._run_ffmpeg(cmd, "copy", "copy video")

    async def _get_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            return float(stdout.decode().strip())
        except ValueError:
            return 600.0  # Default 10 min if unknown

    async def _run_ffmpeg(self, cmd: list, job_id: str, stage: str) -> None:
        """Run an ffmpeg command and log errors."""
        logger.debug(f"[{job_id}] ffmpeg {stage}: {' '.join(cmd[:8])}...")
        proc = await run_async_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"[{job_id}] ffmpeg {stage} failed: {stderr.decode()[-500:]}")
            raise RuntimeError(f"ffmpeg {stage} failed (code {proc.returncode})")

    def _cleanup(self, paths: list) -> None:
        """Clean up temporary files."""
        for p in paths:
            try:
                if p and Path(p).exists():
                    Path(p).unlink()
            except Exception:
                pass
