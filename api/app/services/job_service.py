import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.schemas.upload import JobStatusUpdateRequest

logger = structlog.get_logger()


async def create_job(
    db: AsyncSession,
    *,
    job_id: str,
    filename: str,
    original_filename: str,
    content_type: str,
    s3_raw_key: str,
    file_size: int | None = None,
) -> Job:
    job = Job(
        id=job_id,
        filename=filename,
        original_filename=original_filename,
        content_type=content_type,
        s3_raw_key=s3_raw_key,
        file_size=file_size,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info("job_created", job_id=job_id, filename=filename)
    return job


async def get_job(db: AsyncSession, job_id: str) -> Job | None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession, job_id: str, update: JobStatusUpdateRequest
) -> Job | None:
    job = await get_job(db, job_id)
    if not job:
        return None

    job.status = update.status
    if update.s3_processed_key is not None:
        job.s3_processed_key = update.s3_processed_key
    if update.error_message is not None:
        job.error_message = update.error_message[:2000]

    await db.commit()
    await db.refresh(job)
    logger.info("job_status_updated", job_id=job_id, status=update.status)
    return job
