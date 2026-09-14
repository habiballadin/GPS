variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "gps-fleet"
}

variable "repository_url" {
  description = "Git URL containing this project, accessible by the EC2 instance."
  type        = string
}

variable "repository_ref" {
  type    = string
  default = "gps"
}

variable "instance_type" {
  description = "Keep this at t3.micro for the Free Tier / credit-conserving pilot."
  type        = string
  default     = "t3.micro"
}

variable "admin_cidr" {
  description = "CIDR allowed to access SSH. Use your fixed office IP/32; do not use 0.0.0.0/0."
  type        = string
}

variable "ssh_key_name" {
  description = "Existing EC2 key pair name. Leave empty to use SSM only."
  type        = string
  default     = ""
}

variable "root_volume_gb" {
  description = "Small gp3 boot volume for the pilot host."
  type        = number
  default     = 20
}

variable "alert_email" {
  description = "Optional email endpoint for SNS alerts. The address must be confirmed after apply."
  type        = string
  default     = ""
}

variable "force_destroy_storage" {
  description = "Allow Terraform to delete S3 objects during destroy. Keep false to protect telemetry data."
  type        = bool
  default     = false
}
