import os

import boto3
import structlog
from botocore.exceptions import ClientError

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def _get_s3_client():
    kwargs: dict = {"region_name": settings.aws_region}
    # AWS_ENDPOINT_URL env var routes traffic to LocalStack in local dev;
    # in ECS the variable is absent and the real AWS endpoint is used.
    if endpoint_url := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def generate_presigned_upload_url(
    bucket: str, key: str, content_type: str, expiry: int = 3600
) -> str:
    client = _get_s3_client()
    try:
        url = client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expiry,
        )
        logger.info("presigned_url_generated", bucket=bucket, key=key)
        return url
    except ClientError as exc:
        logger.error("presigned_url_failed", bucket=bucket, key=key, error=str(exc))
        raise


def generate_presigned_download_url(bucket: str, key: str, expiry: int = 3600) -> str:
    client = _get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry,
        )
    except ClientError as exc:
        logger.error("download_url_failed", bucket=bucket, key=key, error=str(exc))
        raise
