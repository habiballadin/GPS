variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "enable_production_platform" {
  description = "Explicit acknowledgement required before planning the paid production platform."
  type        = bool
  default     = false

  validation {
    condition     = var.enable_production_platform
    error_message = "The production platform creates chargeable resources. Deploy the single-EC2 pilot stack in infra/terraform instead. Set enable_production_platform=true only after approving its costs."
  }
}
variable "project_name" {
  type    = string
  default = "gps-fleet"
}
variable "environment" {
  type    = string
  default = "production"
}
variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}
variable "availability_zones" {
  type    = list(string)
  default = []
}
variable "api_image_tag" {
  type    = string
  default = "latest"
}
variable "telemetry_image_tag" {
  type    = string
  default = "latest"
}
variable "api_cpu" {
  type    = number
  default = 512
}
variable "api_memory" {
  type    = number
  default = 1024
}
variable "telemetry_cpu" {
  type    = number
  default = 512
}
variable "telemetry_memory" {
  type    = number
  default = 1024
}
variable "api_desired_count" {
  type    = number
  default = 2
}
variable "telemetry_desired_count" {
  type    = number
  default = 2
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
variable "db_name" {
  type    = string
  default = "fleet"
}
variable "db_username" {
  type    = string
  default = "fleet_admin"
}
variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}
variable "enable_nat_gateway" {
  type    = bool
  default = true
}
variable "enable_iot" {
  type    = bool
  default = false
}
variable "enable_timestream" {
  type    = bool
  default = false
}
variable "enable_opensearch" {
  type    = bool
  default = false
}
variable "enable_redshift" {
  type    = bool
  default = false
}
variable "enable_cloudfront" {
  type    = bool
  default = false
}
variable "enable_waf" {
  type    = bool
  default = true
}
variable "domain_name" {
  type    = string
  default = ""
}
variable "certificate_arn" {
  type    = string
  default = ""
}
