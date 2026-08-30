output "api_endpoint" {
  description = "Public URL of the FastAPI gateway"
  value       = "http://${aws_lb.api.dns_name}"
}

output "raw_bucket_name" {
  description = "S3 bucket for raw video uploads"
  value       = aws_s3_bucket.raw.id
}

output "processed_bucket_name" {
  description = "S3 bucket for transcoded video output"
  value       = aws_s3_bucket.processed.id
}

output "processing_queue_url" {
  description = "SQS URL consumed by worker tasks"
  value       = aws_sqs_queue.processing.url
}

output "dlq_url" {
  description = "Dead-Letter Queue URL — inspect here for failed jobs"
  value       = aws_sqs_queue.dlq.url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cloudwatch_log_groups" {
  description = "CloudWatch log group names"
  value = {
    api    = aws_cloudwatch_log_group.api.name
    worker = aws_cloudwatch_log_group.worker.name
  }
}
