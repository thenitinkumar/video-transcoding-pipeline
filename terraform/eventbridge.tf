# ── EventBridge rule: S3 ObjectCreated → SQS ──────────────────────────────────
# Fires whenever a new object lands under the raw/ prefix in the raw bucket.

resource "aws_cloudwatch_event_rule" "s3_video_upload" {
  name        = "${local.prefix}-s3-video-upload"
  description = "Route raw video upload events to the processing SQS queue"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.raw.id] }
      object = { key = [{ prefix = "raw/" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule      = aws_cloudwatch_event_rule.s3_video_upload.name
  target_id = "SendToProcessingQueue"
  arn       = aws_sqs_queue.processing.arn
}
