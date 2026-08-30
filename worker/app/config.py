from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # AWS — credentials resolved automatically from env vars or ECS task role
    aws_region: str = "us-east-1"

    # S3
    raw_bucket: str = "video-pipeline-raw"
    processed_bucket: str = "video-pipeline-processed"

    # SQS long-polling config
    sqs_queue_url: str = ""
    sqs_wait_time_seconds: int = 20
    sqs_max_messages: int = 1
    sqs_visibility_timeout: int = 300  # Must be > longest expected transcode

    # API — worker reports status back via HTTP
    api_base_url: str = "http://api:8000"
    internal_api_key: str = "change-me-in-production"

    # FFmpeg encoding parameters
    output_video_codec: str = "libx264"
    output_audio_codec: str = "aac"
    output_crf: int = 23          # 0–51; lower = better quality / larger file
    output_preset: str = "medium"  # speed/compression tradeoff
    output_audio_bitrate: str = "128k"
    temp_dir: str = "/tmp/transcoding"


@lru_cache
def get_settings() -> Settings:
    return Settings()
