# ── Dead-Letter Queue ──────────────────────────────────────────────────────────
# Receives messages after maxReceiveCount (3) failed processing attempts.
# Ops teams inspect / replay messages from here.

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.prefix}-dlq"
  message_retention_seconds = 1209600 # 14 days — gives ops time to investigate
}


# ── Main processing queue ──────────────────────────────────────────────────────

resource "aws_sqs_queue" "processing" {
  name                       = "${local.prefix}-processing"
  visibility_timeout_seconds = 300 # Must exceed the longest expected transcode
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20 # Enable long-polling — reduces empty receives

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}


# ── Resource policy: allow EventBridge to enqueue ─────────────────────────────

resource "aws_sqs_queue_policy" "processing" {
  queue_url = aws_sqs_queue.processing.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridge"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.processing.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_cloudwatch_event_rule.s3_video_upload.arn
        }
      }
    }]
  })
}
