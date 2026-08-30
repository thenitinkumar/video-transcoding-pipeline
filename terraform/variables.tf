variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix all resources"
  type        = string
  default     = "vidpipe"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging)"
  type        = string
  default     = "prod"
}

# ── Container images ───────────────────────────────────────────────────────────

variable "api_image_uri" {
  description = "Full ECR image URI for the FastAPI service (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/vidpipe-api:latest)"
  type        = string
}

variable "worker_image_uri" {
  description = "Full ECR image URI for the FFmpeg worker"
  type        = string
}

# ── Networking ─────────────────────────────────────────────────────────────────

variable "vpc_id" {
  description = "VPC in which ECS tasks and the load balancer run"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for ECS Fargate tasks (no public IP needed)"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnets for the Application Load Balancer"
  type        = list(string)
}

# ── Secrets ────────────────────────────────────────────────────────────────────

variable "database_url" {
  description = "PostgreSQL async connection string (e.g. postgresql+asyncpg://user:pass@host/db)"
  type        = string
  sensitive   = true
}

variable "internal_api_key" {
  description = "Shared secret for worker → API internal status-update calls"
  type        = string
  sensitive   = true
}

# ── Auto-scaling ───────────────────────────────────────────────────────────────

variable "sqs_scale_target" {
  description = "Target ApproximateNumberOfMessagesVisible per worker task (triggers scale-out above this)"
  type        = number
  default     = 10
}

variable "worker_min_tasks" {
  description = "Minimum number of worker Fargate tasks (0 = scale to zero when queue is empty)"
  type        = number
  default     = 0
}

variable "worker_max_tasks" {
  description = "Maximum number of worker Fargate tasks"
  type        = number
  default     = 20
}

variable "raw_video_retention_days" {
  description = "Days before raw videos are automatically deleted from S3"
  type        = number
  default     = 7
}
