import os
from pathlib import Path

import ffmpeg
import structlog

from worker.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class TranscodingError(Exception):
    pass


def _probe(input_path: str) -> dict:
    try:
        return ffmpeg.probe(input_path)
    except ffmpeg.Error as exc:
        raise TranscodingError(f"Could not probe file: {exc.stderr.decode()}")


def transcode(input_path: str, output_path: str, job_id: str) -> dict:
    """
    Convert any supported video format to a streaming-optimised H.264 MP4.

    Returns a dict of encoding stats for structured logging.
    """
    log = logger.bind(job_id=job_id)

    probe = _probe(input_path)
    video_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "video"), None
    )
    if not video_stream:
        raise TranscodingError("Input contains no video stream")

    duration = float(probe["format"].get("duration", 0))
    log.info(
        "transcode_started",
        input_codec=video_stream.get("codec_name"),
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        duration_seconds=round(duration, 2),
    )

    try:
        (
            ffmpeg.input(input_path)
            .output(
                output_path,
                vcodec=settings.output_video_codec,
                acodec=settings.output_audio_codec,
                crf=settings.output_crf,
                preset=settings.output_preset,
                audio_bitrate=settings.output_audio_bitrate,
                movflags="+faststart",  # moov atom at front enables progressive streaming
                format="mp4",
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else "unknown"
        log.error("ffmpeg_error", stderr=stderr[-500:])  # last 500 chars avoid flooding
        raise TranscodingError(f"FFmpeg encode failed: {stderr[-300:]}")

    input_bytes = os.path.getsize(input_path)
    output_bytes = os.path.getsize(output_path)
    compression_pct = (1 - output_bytes / input_bytes) * 100 if input_bytes else 0.0

    stats = {
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "compression_pct": round(compression_pct, 1),
        "duration_seconds": round(duration, 2),
    }
    log.info("transcode_completed", **stats)
    return stats


def process_video(input_path: str, job_id: str) -> tuple[str, dict]:
    """Transcode a video and return (output_path, stats)."""
    output_dir = Path(settings.temp_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / "output.mp4")
    stats = transcode(input_path, output_path, job_id)
    return output_path, stats
