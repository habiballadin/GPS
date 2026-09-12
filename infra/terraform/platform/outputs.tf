output "api_url" {
  value = "http://${aws_lb.api.dns_name}"
}

output "api_load_balancer_dns" {
  value = aws_lb.api.dns_name
}

output "device_load_balancer_dns" {
  value = aws_lb.device.dns_name
}

output "teltonika_endpoint" {
  value = "${aws_lb.device.dns_name}:5001"
}

output "concox_endpoint" {
  value = "${aws_lb.device.dns_name}:5002"
}

output "aurora_endpoint" {
  value = aws_rds_cluster.this.endpoint
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "api_ecr_repository" {
  value = aws_ecr_repository.api.repository_url
}

output "telemetry_ecr_repository" {
  value = aws_ecr_repository.telemetry.repository_url
}

output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "timestream_database" {
  value = var.enable_timestream ? aws_timestreamwrite_database.this[0].database_name : null
}
