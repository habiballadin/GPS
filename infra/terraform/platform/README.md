# Production AWS Terraform blueprint

This directory provisions the paid production architecture for the custom GPS platform without Traccar. It is deliberately blocked by default to protect Free Tier credits. Use the single-EC2 pilot stack in `infra/terraform` for the current deployment.

- VPC with public/private subnets and optional NAT gateways
- ECS Fargate API and custom TCP telemetry gateway
- Application Load Balancer for the API
- Network Load Balancer on TCP `5001` (Teltonika FMB920) and `5002` (CONCOX V5)
- Aurora PostgreSQL, ElastiCache Redis, S3, Secrets Manager, CloudWatch Logs
- ECR repositories, SQS queues, Kinesis, and optional Timestream

The existing low-cost EC2 deployment remains in `infra/terraform` and is not changed by this stack.

## Use

```bash
cp terraform.tfvars.example terraform.tfvars
# Set enable_production_platform = true only after approving recurring costs.
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

Build and push the API and telemetry container images to the ECR repositories before expecting ECS tasks to become healthy. The ECS task execution and task roles are intentionally managed here; the AWS principal applying this stack must have IAM role-creation permissions. The current deployment user previously lacked `iam:CreateRole`, so an administrator must grant that permission or pre-provision the roles.

Review the plan carefully: Aurora, Redis, Fargate, NAT gateways, and public load balancers create ongoing AWS charges. Do not apply this production stack until the account permissions, image pipeline, domain/TLS setup, and cost budget are approved.
