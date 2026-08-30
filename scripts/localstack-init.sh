#!/usr/bin/env bash
# Bootstraps local AWS resources in LocalStack on startup.
set -e

echo "==> Creating S3 buckets..."
awslocal s3 mb s3://video-pipeline-raw
awslocal s3 mb s3://video-pipeline-processed

echo "==> Creating SQS DLQ..."
awslocal sqs create-queue --queue-name video-pipeline-dlq

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/video-pipeline-dlq \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

echo "==> Creating SQS processing queue with DLQ (maxReceiveCount=3)..."
awslocal sqs create-queue \
  --queue-name video-pipeline-processing \
  --attributes "{
    \"VisibilityTimeout\": \"300\",
    \"ReceiveMessageWaitTimeSeconds\": \"20\",
    \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
  }"

QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/video-pipeline-processing \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

echo "==> Configuring S3 → EventBridge notification on raw bucket..."
awslocal s3api put-bucket-notification-configuration \
  --bucket video-pipeline-raw \
  --notification-configuration '{"EventBridgeConfiguration": {}}'

echo "==> Creating EventBridge rule for S3 ObjectCreated events..."
awslocal events put-rule \
  --name s3-video-upload-rule \
  --event-pattern '{
    "source": ["aws.s3"],
    "detail-type": ["Object Created"],
    "detail": {
      "bucket": {"name": ["video-pipeline-raw"]},
      "object": {"key": [{"prefix": "raw/"}]}
    }
  }' \
  --state ENABLED

echo "==> Adding SQS target to EventBridge rule..."
awslocal events put-targets \
  --rule s3-video-upload-rule \
  --targets "[{\"Id\": \"sqs-target\", \"Arn\": \"${QUEUE_ARN}\"}]"

echo "==> LocalStack bootstrap complete."
