resource "aws_iam_role" "app" {
  name = "${var.project_name}-ec2-ssm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Name = "${var.project_name}-ec2-ssm-role" }
}

resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.app.name
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "telemetry" {
  bucket        = "${var.project_name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}-telemetry"
  force_destroy = var.force_destroy_storage
  tags          = { Name = "${var.project_name}-telemetry" }
}

resource "aws_s3_bucket_public_access_block" "telemetry" {
  bucket                  = aws_s3_bucket.telemetry.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  rule {
    id     = "expire-raw-telemetry"
    status = "Enabled"
    filter { prefix = "telemetry/" }
    expiration { days = 30 }
  }
}

resource "aws_dynamodb_table" "device_state" {
  name         = "${var.project_name}-device-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  attribute {
    name = "device_id"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_sqs_queue" "telemetry_dlq" {
  name                      = "${var.project_name}-telemetry-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "telemetry" {
  name                       = "${var.project_name}-telemetry"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.telemetry_dlq.arn, maxReceiveCount = 3 })
}

resource "aws_sns_topic" "alerts" { name = "${var.project_name}-alerts" }

resource "aws_cloudwatch_log_group" "heartbeat" {
  name              = "/aws/lambda/${var.project_name}-telemetry-heartbeat"
  retention_in_days = 7
}

resource "aws_iam_role" "heartbeat" {
  name               = "${var.project_name}-telemetry-heartbeat-role"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "heartbeat" {
  name = "${var.project_name}-telemetry-heartbeat"
  role = aws_iam_role.heartbeat.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.heartbeat.arn}:*" },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.telemetry.arn}/telemetry/*" },
    { Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = aws_dynamodb_table.device_state.arn },
    { Effect = "Allow", Action = ["sns:Publish"], Resource = aws_sns_topic.alerts.arn },
    { Effect = "Allow", Action = ["sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ReceiveMessage"], Resource = aws_sqs_queue.telemetry.arn }
  ] })
}

data "archive_file" "heartbeat" {
  type        = "zip"
  source_file = "${path.module}/lambda/heartbeat.py"
  output_path = "${path.module}/lambda/heartbeat.zip"
}

resource "aws_lambda_function" "heartbeat" {
  function_name    = "${var.project_name}-telemetry-heartbeat"
  role             = aws_iam_role.heartbeat.arn
  handler          = "heartbeat.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.heartbeat.output_path
  source_code_hash = data.archive_file.heartbeat.output_base64sha256
  timeout          = 15
  memory_size      = 128
  environment { variables = { TELEMETRY_BUCKET = aws_s3_bucket.telemetry.bucket, DEVICE_STATE_TABLE = aws_dynamodb_table.device_state.name, ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn } }
  depends_on = [aws_cloudwatch_log_group.heartbeat]
}

resource "aws_lambda_event_source_mapping" "telemetry" {
  event_source_arn = aws_sqs_queue.telemetry.arn
  function_name    = aws_lambda_function.heartbeat.arn
  batch_size       = 1
}

resource "aws_cloudwatch_event_rule" "telemetry_heartbeat" {
  name                = "${var.project_name}-telemetry-heartbeat"
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "telemetry_heartbeat" {
  rule  = aws_cloudwatch_event_rule.telemetry_heartbeat.name
  arn   = aws_sqs_queue.telemetry.arn
  input = jsonencode({ source = "eventbridge", type = "telemetry_heartbeat" })
}

resource "aws_sqs_queue_policy" "allow_eventbridge" {
  queue_url = aws_sqs_queue.telemetry.id
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.telemetry.arn, Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.telemetry_heartbeat.arn } } }] })
}

resource "aws_ecr_repository" "app" {
  name                 = "${var.project_name}-app"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "web" {
  name                 = "${var.project_name}-web-console"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
