import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.job import JobStatus
from app.schemas.upload import (
    JobStatusResponse,
    JobStatusUpdateRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import job_service, s3_service

router = APIRouter(prefix="/uploads", tags=["uploads"])
logger = structlog.get_logger()
settings = get_settings()


@router.post("", response_model=UploadInitResponse, status_code=201)
async def initiate_upload(
    body: UploadInitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1 of the upload flow: generates a presigned S3 PUT URL so the client
    can push the video file directly to S3 without routing it through this server.
    """
    job_id = str(uuid.uuid4())
    raw_ext = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else "mp4"
    s3_key = f"raw/{job_id}/{body.filename}"

    try:
        presigned_url = s3_service.generate_presigned_upload_url(
            bucket=settings.raw_bucket,
            key=s3_key,
            content_type=body.content_type,
            expiry=settings.presigned_url_expiry,
        )
    except Exception as exc:
        logger.error("presigned_url_error", error=str(exc))
        raise HTTPException(status_code=503, detail="Could not generate upload URL")

    await job_service.create_job(
        db,
        job_id=job_id,
        filename=f"{job_id}.{raw_ext}",
        original_filename=body.filename,
        content_type=body.content_type,
        s3_raw_key=s3_key,
        file_size=body.file_size,
    )

    logger.info("upload_initiated", job_id=job_id, filename=body.filename)
    return UploadInitResponse(
        job_id=job_id,
        presigned_url=presigned_url,
        s3_key=s3_key,
        expires_in=settings.presigned_url_expiry,
    )


@router.post("/{job_id}/confirm", response_model=JobStatusResponse)
async def confirm_upload(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Step 2 (optional): client calls this after the S3 PUT completes to
    transition the job to QUEUED. The SQS/EventBridge trigger is the real
    signal to workers; this endpoint just improves status observability.
    """
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.PENDING:
        return job

    updated = await job_service.update_job_status(
        db, job_id, JobStatusUpdateRequest(status=JobStatus.QUEUED)
    )
    return updated
