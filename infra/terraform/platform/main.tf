data "aws_availability_zones" "available" { state = "available" }

locals {
  azs  = length(var.availability_zones) > 0 ? var.availability_zones : slice(data.aws_availability_zones.available.names, 0, 2)
  name = "${var.project_name}-${var.environment}"
  tags = { Project = var.project_name, Environment = var.environment, ManagedBy = "terraform" }
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "jwt" {
  length  = 64
  special = true
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(local.tags, { Name = "${local.name}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.name}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(local.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = merge(local.tags, { Name = "${local.name}-public-${count.index + 1}" })
}

resource "aws_subnet" "private" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags              = merge(local.tags, { Name = "${local.name}-private-${count.index + 1}" })
}

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? length(local.azs) : 0
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${local.name}-nat-${count.index + 1}" })
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? length(local.azs) : 0
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  depends_on    = [aws_internet_gateway.this]
  tags          = merge(local.tags, { Name = "${local.name}-nat-${count.index + 1}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(local.tags, { Name = "${local.name}-public-routes" })
}

resource "aws_route_table_association" "public" {
  count          = length(local.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = length(local.azs)
  vpc_id = aws_vpc.this.id
  dynamic "route" {
    for_each = var.enable_nat_gateway ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.this[count.index].id
    }
  }
  tags = merge(local.tags, { Name = "${local.name}-private-routes-${count.index + 1}" })
}

resource "aws_route_table_association" "private" {
  count          = length(local.azs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public API access"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_security_group" "ecs" {
  name        = "${local.name}-ecs"
  description = "Private ECS services"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    from_port   = 5001
    to_port     = 5002
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_security_group" "data" {
  name        = "${local.name}-data"
  description = "Database and cache access"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = 30
  tags              = local.tags
}
resource "aws_cloudwatch_log_group" "telemetry" {
  name              = "/ecs/${local.name}/telemetry"
  retention_in_days = 30
  tags              = local.tags
}

resource "aws_ecr_repository" "api" {
  name = "${local.name}/api"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}
resource "aws_ecr_repository" "telemetry" {
  name = "${local.name}/telemetry"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

resource "aws_s3_bucket" "raw" {
  bucket_prefix = "${local.name}-raw-"
  tags          = local.tags
}
resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${local.name}-documents-"
  tags          = local.tags
}
resource "aws_s3_bucket" "web" {
  bucket_prefix = "${local.name}-web-"
  tags          = local.tags
}
resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_secretsmanager_secret" "app" {
  name_prefix = "${local.name}-app-"
  tags        = local.tags
}
resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({ jwt_secret = random_password.jwt.result })
}

resource "aws_db_subnet_group" "this" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
  tags       = local.tags
}
resource "aws_rds_cluster" "this" {
  cluster_identifier      = local.name
  engine                  = "aurora-postgresql"
  database_name           = var.db_name
  master_username         = var.db_username
  master_password         = random_password.db.result
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.data.id]
  storage_encrypted       = true
  backup_retention_period = 7
  skip_final_snapshot     = true
  tags                    = local.tags
}
resource "aws_rds_cluster_instance" "this" {
  count                = 2
  identifier           = "${local.name}-${count.index + 1}"
  cluster_identifier   = aws_rds_cluster.this.id
  instance_class       = var.db_instance_class
  engine               = aws_rds_cluster.this.engine
  db_subnet_group_name = aws_db_subnet_group.this.name
  tags                 = local.tags
}

resource "aws_elasticache_subnet_group" "this" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}
resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = replace(local.name, "_", "-")
  description                = "${local.name} Redis"
  node_type                  = var.redis_node_type
  num_cache_clusters         = 2
  engine                     = "redis"
  port                       = 6379
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.data.id]
  tags                       = local.tags
}

resource "aws_lb" "api" {
  name               = substr("${local.name}-api", 0, 32)
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]
  tags               = local.tags
}
resource "aws_lb_target_group" "api" {
  name        = substr("${local.name}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id
  health_check {
    path    = "/health"
    matcher = "200"
  }
}
resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb" "device" {
  name               = substr("${local.name}-device", 0, 32)
  load_balancer_type = "network"
  subnets            = aws_subnet.public[*].id
  tags               = local.tags
}
resource "aws_lb_target_group" "teltonika" {
  name        = substr("${local.name}-teltonika", 0, 32)
  port        = 5001
  protocol    = "TCP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id
}
resource "aws_lb_target_group" "concox" {
  name        = substr("${local.name}-concox", 0, 32)
  port        = 5002
  protocol    = "TCP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id
}
resource "aws_lb_listener" "teltonika" {
  load_balancer_arn = aws_lb.device.arn
  port              = 5001
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.teltonika.arn
  }
}
resource "aws_lb_listener" "concox" {
  load_balancer_arn = aws_lb.device.arn
  port              = 5002
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.concox.arn
  }
}

resource "aws_ecs_cluster" "this" {
  name = local.name
  tags = local.tags
}
resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role" "ecs_task" {
  name               = "${local.name}-ecs-task"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = local.tags
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name             = "api"
    image            = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
    essential        = true
    portMappings     = [{ containerPort = 8000, protocol = "tcp" }]
    environment      = [{ name = "DATABASE_HOST", value = aws_rds_cluster.this.endpoint }, { name = "REDIS_HOST", value = aws_elasticache_replication_group.this.primary_endpoint_address }]
    secrets          = [{ name = "JWT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:jwt_secret::" }]
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.api.name, awslogs-region = var.aws_region, awslogs-stream-prefix = "api" } }
  }])
}
resource "aws_ecs_task_definition" "telemetry" {
  family                   = "${local.name}-telemetry"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.telemetry_cpu
  memory                   = var.telemetry_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name             = "telemetry"
    image            = "${aws_ecr_repository.telemetry.repository_url}:${var.telemetry_image_tag}"
    essential        = true
    portMappings     = [{ containerPort = 5001, protocol = "tcp" }, { containerPort = 5002, protocol = "tcp" }]
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.telemetry.name, awslogs-region = var.aws_region, awslogs-stream-prefix = "telemetry" } }
  }])
}
resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener.api]
  tags       = local.tags
}
resource "aws_ecs_service" "telemetry" {
  name            = "telemetry"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.telemetry.arn
  desired_count   = var.telemetry_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.teltonika.arn
    container_name   = "telemetry"
    container_port   = 5001
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.concox.arn
    container_name   = "telemetry"
    container_port   = 5002
  }
  depends_on = [aws_lb_listener.teltonika, aws_lb_listener.concox]
  tags       = local.tags
}

resource "aws_sqs_queue" "telemetry_dlq" {
  name = "${local.name}-telemetry-dlq"
  tags = local.tags
}
resource "aws_sqs_queue" "telemetry" {
  name           = "${local.name}-telemetry"
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.telemetry_dlq.arn, maxReceiveCount = 5 })
  tags           = local.tags
}
resource "aws_sqs_queue" "notifications" {
  name = "${local.name}-notifications"
  tags = local.tags
}
resource "aws_kinesis_stream" "telemetry" {
  name             = "${local.name}-telemetry"
  shard_count      = 1
  retention_period = 24
  stream_mode_details {
    stream_mode = "PROVISIONED"
  }
  tags = local.tags
}

resource "aws_timestreamwrite_database" "this" {
  count         = var.enable_timestream ? 1 : 0
  database_name = local.name
}
resource "aws_timestreamwrite_table" "telemetry" {
  count         = var.enable_timestream ? 1 : 0
  database_name = aws_timestreamwrite_database.this[0].database_name
  table_name    = "telemetry"
  retention_properties {
    memory_store_retention_period_in_hours  = 24
    magnetic_store_retention_period_in_days = 365
  }
}
