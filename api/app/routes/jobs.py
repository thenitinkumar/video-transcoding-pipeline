import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.upload import JobStatusResponse, JobStatusUpdateRequest
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = structlog.get_logger()
settings = get_settings()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve the current processing status of a transcoding job."""
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}/status", response_model=JobStatusResponse)
async def update_job_status(
    job_id: str,
    body: JobStatusUpdateRequest,
    x_internal_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint: workers call this to report PROCESSING / COMPLETED / FAILED.
    Protected by a shared secret; not intended to be publicly reachable.
    """
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    job = await job_service.update_job_status(db, job_id, body)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info("worker_status_update", job_id=job_id, status=body.status)
    return job
