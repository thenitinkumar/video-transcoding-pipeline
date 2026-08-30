"""
SQS consumer / video transcoding worker.

Lifecycle per message
─────────────────────
1. Receive message from SQS (long-poll, 1 at a time)
2. Parse S3 event → extract bucket + key → derive job_id
3. PATCH job to PROCESSING via API
4. Download raw video from S3 to /tmp
5. Transcode with FFmpeg → H.264 MP4
6. Upload result to processed-videos S3 bucket
7. PATCH job to COMPLETED
8. Delete SQS message

If any step raises, the message is NOT deleted so SQS will redeliver up to
maxReceiveCount times before routing to the Dead-Letter Queue.
"""

import json
import logging
import os
import shutil
import signal
import threading
import time
from pathlib import Path

import boto3
import requests
import structlog

from worker.config import get_settings
from worker.transcoder import TranscodingError, process_video

# ── Structured JSON logging ────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logging.basicConfig(level=logging.INFO)
# ──────────────────────────────────────────────────────────────────────────────

logger = structlog.get_logger()
settings = get_settings()
_shutdown = threading.Event()


# ── AWS client factory ─────────────────────────────────────────────────────────

def _boto_kwargs() -> dict:
    kwargs: dict = {"region_name": settings.aws_region}
    if url := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = url
    return kwargs


def _sqs():
    return boto3.client("sqs", **_boto_kwargs())


def _s3():
    return boto3.client("s3", **_boto_kwargs())


# ── API status reporting ───────────────────────────────────────────────────────

def _patch_status(
    job_id: str,
    status: str,
    s3_processed_key: str | None = None,
    error: str | None = None,
) -> None:
    payload: dict = {"status": status}
    if s3_processed_key:
        payload["s3_processed_key"] = s3_processed_key
    if error:
        payload["error_message"] = error[:1000]

    try:
        resp = requests.patch(
            f"{settings.api_base_url}/api/v1/jobs/{job_id}/status",
            json=payload,
            headers={"x-internal-key": settings.internal_api_key},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        # Log but don't crash — status update failure shouldn't block processing
        logger.warning("status_update_failed", job_id=job_id, error=str(exc))


# ── Event parsing ──────────────────────────────────────────────────────────────

def _parse_s3_events(body: str) -> list[dict]:
    """
    Extract S3 bucket+key pairs from either an EventBridge event or a direct
    S3 notification payload (both routed through SQS).
    """
    data = json.loads(body)

    if "detail" in data:
        # EventBridge format: {"source": "aws.s3", "detail-type": "Object Created", ...}
        d = data["detail"]
        return [{"bucket": d["bucket"]["name"], "key": d["object"]["key"]}]

    if "Records" in data:
        return [
            {"bucket": r["s3"]["bucket"]["name"], "key": r["s3"]["object"]["key"]}
            for r in data["Records"]
            if r.get("eventName", "").startswith("ObjectCreated")
        ]

    return []


# ── Core message processor ─────────────────────────────────────────────────────

def _handle_message(sqs_client, s3_client, message: dict) -> None:
    receipt = message["ReceiptHandle"]
    log = logger.bind(receipt=receipt[:16])

    events = _parse_s3_events(message["Body"])
    if not events:
        log.warning("no_s3_events")
        sqs_client.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt)
        return

    for event in events:
        raw_key: str = event["key"]
        bucket: str = event["bucket"]

        # Key format: raw/{job_id}/{filename}
        parts = raw_key.split("/", 2)
        if len(parts) != 3 or parts[0] != "raw":
            log.warning("unexpected_key_format", key=raw_key)
            continue

        job_id, filename = parts[1], parts[2]
        log = log.bind(job_id=job_id)

        work_dir = Path(settings.temp_dir) / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        input_path = str(work_dir / filename)

        try:
            _patch_status(job_id, "PROCESSING")

            log.info("downloading", bucket=bucket, key=raw_key)
            s3_client.download_file(bucket, raw_key, input_path)

            log.info("transcoding")
            output_path, stats = process_video(input_path, job_id)

            processed_key = f"processed/{job_id}/output.mp4"
            log.info("uploading", processed_key=processed_key)
            s3_client.upload_file(
                output_path,
                settings.processed_bucket,
                processed_key,
                ExtraArgs={"ContentType": "video/mp4"},
            )

            _patch_status(job_id, "COMPLETED", s3_processed_key=processed_key)
            log.info("job_done", **stats)

        except TranscodingError as exc:
            log.error("transcode_failed", error=str(exc))
            _patch_status(job_id, "FAILED", error=str(exc))
            raise  # Do NOT delete message — let SQS retry / route to DLQ

        except Exception as exc:
            log.error("unexpected_error", error=str(exc))
            _patch_status(job_id, "FAILED", error=str(exc))
            raise

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # Only delete after all events in this message have been processed
    sqs_client.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=receipt)
    log.info("message_deleted")


# ── Main polling loop ──────────────────────────────────────────────────────────

def run() -> None:
    logger.info("worker_starting", queue_url=settings.sqs_queue_url)
    sqs = _sqs()
    s3 = _s3()

    while not _shutdown.is_set():
        try:
            resp = sqs.receive_message(
                QueueUrl=settings.sqs_queue_url,
                MaxNumberOfMessages=settings.sqs_max_messages,
                WaitTimeSeconds=settings.sqs_wait_time_seconds,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception as exc:
            logger.error("sqs_receive_error", error=str(exc))
            time.sleep(5)
            continue

        for msg in resp.get("Messages", []):
            receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
            logger.info("message_received", receive_count=receive_count)
            try:
                _handle_message(sqs, s3, msg)
            except Exception:
                pass  # Already logged; leave message in queue for SQS retry

    logger.info("worker_stopped")


def _on_signal(signum, _frame):
    logger.info("shutdown_requested", signal=signum)
    _shutdown.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    run()
