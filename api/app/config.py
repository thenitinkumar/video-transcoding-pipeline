import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # AWS — credentials come from env vars or ECS task IAM role automatically
    aws_region: str = "us-east-1"

    # S3
    raw_bucket: str = "video-pipeline-raw"
    processed_bucket: str = "video-pipeline-processed"
    presigned_url_expiry: int = 3600

    # SQS
    sqs_queue_url: str = ""

    # PostgreSQL (swap DATABASE_URL env var for RDS in production)
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/video_pipeline"
    )

    # App
    app_name: str = "Video Transcoding Pipeline"
    debug: bool = False

    # Shared secret used by workers to call internal status-update endpoints
    internal_api_key: str = "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
