from datetime import datetime

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class UploadInitRequest(BaseModel):
    filename: str = Field(..., description="Original filename including extension")
    content_type: str = Field(default="video/mp4")
    file_size: int | None = Field(None, description="File size in bytes")


class UploadInitResponse(BaseModel):
    job_id: str
    presigned_url: str
    s3_key: str
    expires_in: int


class JobStatusResponse(BaseModel):
    job_id: str
    filename: str
    original_filename: str
    status: JobStatus
    s3_raw_key: str
    s3_processed_key: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobStatusUpdateRequest(BaseModel):
    status: JobStatus
    s3_processed_key: str | None = None
    error_message: str | None = None
