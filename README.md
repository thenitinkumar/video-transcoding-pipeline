# Video Transcoding Pipeline

An automated, event-driven video transcoding pipeline built with **FastAPI**, **AWS SQS**, **ECS Fargate**, and **FFmpeg**. Upload a raw video — the system converts it to a streaming-optimised H.264 MP4 automatically, at any scale, with zero idle cost.

```
[ Client ] ──► [ FastAPI Gateway ] ──► [ S3 Raw Bucket ]
                      │                       │
               (job created)          (S3 event fires)
                                             │
                                      [ EventBridge ]
                                             │
                                        [ SQS Queue ] ◄── Dead-Letter Queue (×3 retries)
                                             │
                                    [ ECS Fargate Workers ]
                                    Python · FFmpeg · auto-scale
                                             │
                                    [ S3 Processed Bucket ]
                                    H.264 MP4 · +faststart
```

---

## Why this architecture?

| Problem | Solution |
|---|---|
| Raw video files are huge — routing them through the API server would block all other requests | **Presigned S3 URLs** — client uploads directly to S3, the API never touches the bytes |
| Video encoding is slow and CPU-heavy | **Async workers** on ECS Fargate — encoding is fully decoupled from the API |
| 1,000 videos arrive at once and could overwhelm workers | **SQS queue** acts as a buffer — jobs wait safely, nothing is dropped |
| Workers should not run (and cost money) when idle | **Scale-to-zero** — ECS desired count starts at 0, auto-scaling adds tasks as the queue fills |
| A corrupted video could crash workers in a loop | **Dead-Letter Queue** — after 3 failed attempts a message is quarantined, healthy jobs continue |

---

## Features

- **S3 Presigned Upload URLs** — API stays lightweight; clients push video bytes directly to S3
- **EventBridge → SQS** event bus — fully decoupled, no polling from the API side
- **FFmpeg H.264 encoding** — converts any input format to streaming-optimised MP4 with `+faststart`
- **Target-tracking auto-scaling** — ECS tasks scale on `ApproximateNumberOfMessagesVisible`; scales down to zero when queue is empty
- **Dead-Letter Queue** — corrupted uploads are isolated after 3 retries, never blocking the queue
- **Structured JSON logging** via `structlog` — every event is CloudWatch / Datadog queryable
- **Job status API** — poll `GET /api/v1/jobs/{id}` for `PENDING → PROCESSING → COMPLETED / FAILED`
- **Full Terraform IaC** — one `terraform apply` provisions the entire AWS stack
- **Local dev stack** — `docker compose up` runs the full pipeline with LocalStack (no real AWS needed)

---

## Project Structure

```
.
├── api/                        # FastAPI gateway service
│   ├── app/
│   │   ├── main.py             # App entrypoint, structlog config
│   │   ├── config.py           # Settings via pydantic-settings
│   │   ├── database.py         # Async SQLAlchemy + PostgreSQL
│   │   ├── models/job.py       # Job ORM model
│   │   ├── schemas/upload.py   # Pydantic request/response schemas
│   │   ├── routes/
│   │   │   ├── uploads.py      # POST /uploads, POST /uploads/:id/confirm
│   │   │   └── jobs.py         # GET /jobs/:id, PATCH /jobs/:id/status
│   │   └── services/
│   │       ├── s3_service.py   # Presigned URL generation
│   │       └── job_service.py  # Job CRUD (async)
│   ├── requirements.txt
│   └── Dockerfile
│
├── worker/                     # SQS consumer + FFmpeg transcoder
│   ├── app/
│   │   ├── worker.py           # SQS long-poll loop, SIGTERM handler
│   │   ├── transcoder.py       # ffmpeg-python H.264 encode pipeline
│   │   └── config.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── terraform/                  # AWS infrastructure as code
│   ├── main.tf                 # Provider, locals
│   ├── variables.tf
│   ├── outputs.tf
│   ├── s3.tf                   # Raw + processed buckets, EventBridge notification
│   ├── sqs.tf                  # Processing queue + Dead-Letter Queue
│   ├── eventbridge.tf          # S3 ObjectCreated → SQS rule
│   ├── iam.tf                  # Least-privilege task roles
│   └── ecs.tf                  # Cluster, task definitions, ALB, auto-scaling
│
├── scripts/
│   └── localstack-init.sh      # Bootstraps S3/SQS/EventBridge in LocalStack
│
├── docker-compose.yml          # Full local dev stack
└── .env.example                # All required environment variables
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [AWS CLI](https://aws.amazon.com/cli/) (for real deployments)
- [Terraform ≥ 1.6](https://developer.hashicorp.com/terraform/install) (for real deployments)

### Local Development (LocalStack — no real AWS needed)

```bash
# 1. Clone the repo
git clone https://github.com/thenitinkumar/video-transcoding-pipeline.git
cd video-transcoding-pipeline

# 2. Start everything
docker compose up --build

# API is available at http://localhost:8000
# LocalStack runs at http://localhost:4566
```

`docker compose up` will:
1. Start PostgreSQL
2. Start LocalStack and run `scripts/localstack-init.sh` — which creates both S3 buckets, the SQS queue, the DLQ, and the EventBridge rule automatically
3. Start the FastAPI gateway
4. Start a worker process connected to the local queue

---

## API Usage

### 1 — Initiate an upload

```bash
curl -X POST http://localhost:8000/api/v1/uploads \
  -H "Content-Type: application/json" \
  -d '{"filename": "my-video.mov", "content_type": "video/quicktime"}'
```

**Response:**
```json
{
  "job_id": "3f2a1c8e-...",
  "presigned_url": "https://s3.amazonaws.com/...",
  "s3_key": "raw/3f2a1c8e-.../my-video.mov",
  "expires_in": 3600
}
```

### 2 — Upload directly to S3

Use the `presigned_url` from step 1. The API server is never involved.

```bash
curl -X PUT "<presigned_url>" \
  -H "Content-Type: video/quicktime" \
  --data-binary @my-video.mov
```

### 3 — (Optional) Confirm the upload

```bash
curl -X POST http://localhost:8000/api/v1/uploads/3f2a1c8e-.../confirm
```

### 4 — Poll for job status

```bash
curl http://localhost:8000/api/v1/jobs/3f2a1c8e-...
```

**Response when complete:**
```json
{
  "job_id": "3f2a1c8e-...",
  "filename": "my-video.mov",
  "status": "COMPLETED",
  "s3_raw_key": "raw/3f2a1c8e-.../my-video.mov",
  "s3_processed_key": "processed/3f2a1c8e-.../output.mp4",
  "created_at": "2026-08-31T10:00:00Z",
  "updated_at": "2026-08-31T10:04:23Z"
}
```

### Job Status Flow

```
PENDING  →  QUEUED  →  PROCESSING  →  COMPLETED
                                   ↘  FAILED (check error_message)
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values.

| Variable | Service | Description |
|---|---|---|
| `AWS_REGION` | both | AWS region (default: `us-east-1`) |
| `RAW_BUCKET` | both | S3 bucket for raw video uploads |
| `PROCESSED_BUCKET` | both | S3 bucket for transcoded output |
| `SQS_QUEUE_URL` | worker | Full SQS queue URL |
| `DATABASE_URL` | api | PostgreSQL async connection string |
| `INTERNAL_API_KEY` | both | Shared secret for worker→API status updates |
| `API_BASE_URL` | worker | Base URL of the FastAPI service |
| `AWS_ENDPOINT_URL` | both | Set to `http://localhost:4566` for LocalStack only |
| `OUTPUT_CRF` | worker | FFmpeg CRF quality (0–51, default `23`) |
| `OUTPUT_PRESET` | worker | FFmpeg speed/compression preset (default `medium`) |

In production on ECS Fargate, leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` blank — the task IAM role is used automatically.

---

## Deploying to AWS with Terraform

### 1 — Build and push container images

```bash
# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push API image
docker build -t vidpipe-api ./api
docker tag vidpipe-api:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-api:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-api:latest

# Build and push worker image
docker build -t vidpipe-worker ./worker
docker tag vidpipe-worker:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-worker:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-worker:latest
```

### 2 — Apply Terraform

```bash
cd terraform

terraform init

terraform apply \
  -var="api_image_uri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-api:latest" \
  -var="worker_image_uri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/vidpipe-worker:latest" \
  -var="vpc_id=vpc-xxxxxxxx" \
  -var="private_subnet_ids=[\"subnet-aaa\",\"subnet-bbb\"]" \
  -var="public_subnet_ids=[\"subnet-ccc\",\"subnet-ddd\"]" \
  -var="database_url=postgresql+asyncpg://user:pass@your-rds-host/video_pipeline" \
  -var="internal_api_key=$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

### 3 — Outputs

After apply, Terraform prints:

```
api_endpoint            = "http://vidpipe-prod-api-123456789.us-east-1.elb.amazonaws.com"
raw_bucket_name         = "vidpipe-prod-raw-123456789012"
processed_bucket_name   = "vidpipe-prod-processed-123456789012"
processing_queue_url    = "https://sqs.us-east-1.amazonaws.com/123456789012/vidpipe-prod-processing"
dlq_url                 = "https://sqs.us-east-1.amazonaws.com/123456789012/vidpipe-prod-dlq"
cloudwatch_log_groups   = { api = "/ecs/vidpipe-prod/api", worker = "/ecs/vidpipe-prod/worker" }
```

---

## Auto-Scaling Behaviour

The worker service uses **target-tracking scaling** on the SQS `ApproximateNumberOfMessagesVisible` metric.

| Queue Depth | Worker Tasks | Notes |
|---|---|---|
| 0 | **0** | Full scale-to-zero — no idle cost |
| 1 – 10 | 1 | Single worker drains the queue |
| 11 – 50 | 2 – 5 | Linear scale-out at 10 msgs/task |
| 100+ | up to 20 | Configurable via `worker_max_tasks` |
| Poison pill (×3 fail) | — | Routed to DLQ, queue continues |

Scale-out cooldown: **60s** — reacts quickly to bursts.  
Scale-in cooldown: **300s** — lets tasks finish encoding before terminating.

---

## Observability

All logs are structured JSON, emitted via `structlog`:

```json
{"event": "job_done", "job_id": "3f2a1c8e-...", "input_bytes": 524288000,
 "output_bytes": 98304000, "compression_pct": 81.3, "duration_seconds": 127.4,
 "level": "info", "timestamp": "2026-08-31T10:04:23Z"}
```

**CloudWatch Logs Insights query** — find all failed jobs in the last hour:

```
fields @timestamp, job_id, error_message
| filter event = "transcode_failed"
| sort @timestamp desc
| limit 20
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.115, Python 3.12 |
| Database | PostgreSQL via async SQLAlchemy 2.0 |
| Object storage | AWS S3 |
| Message queue | AWS SQS (long-polling, DLQ) |
| Event routing | AWS EventBridge |
| Compute | AWS ECS Fargate |
| Video encoding | FFmpeg via `ffmpeg-python` |
| Logging | `structlog` (JSON output) |
| Infrastructure | Terraform ≥ 1.6, AWS Provider ~5.0 |
| Local dev | Docker Compose + LocalStack |

---

## License

MIT
