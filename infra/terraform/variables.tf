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
  type    = string
  default = "t3.small"
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
  type    = number
  default = 30
}
