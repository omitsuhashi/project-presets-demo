terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 6.67.0, < 7.0" }
  }
}

variable "name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,18}[a-z0-9]$", var.name))
    error_message = "Use 3-20 lowercase letters, digits and hyphens, starting with a letter."
  }
}
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "image_uri" {
  type = string
  # Empty only during initial foundation creation; callers must supply this input.
  validation {
    condition     = var.image_uri == "" || can(regex("@sha256:[a-f0-9]{64}$", var.image_uri))
    error_message = "Pin the image by digest; mutable image tags are not deployments."
  }
}
variable "container_port" { type = number }
variable "health_check_path" { type = string }
variable "environment" {
  type    = map(string)
  default = {}
}
variable "secret_arns" {
  type    = map(string)
  default = {}
  validation {
    condition     = alltrue([for arn in values(var.secret_arns) : can(regex("^arn:aws:(secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+|ssm:[a-z0-9-]+:[0-9]{12}:parameter/[A-Za-z0-9_./-]+)$", arn))])
    error_message = "Use literal Secrets Manager or SSM parameter ARNs; wildcard permissions and secret values are not supported."
  }
}
variable "cpu" {
  type    = number
  default = 256
}
variable "memory" {
  type    = number
  default = 512
}
variable "desired_count" {
  type    = number
  default = 1
}
variable "assign_public_ip" {
  type    = bool
  default = true
}
variable "certificate_arn" {
  type    = string
  default = null
}

data "aws_region" "current" {}
resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_cloudwatch_log_group" "app" {
  name              = "/project-presets/${var.name}"
  retention_in_days = 30
}
resource "aws_ecs_cluster" "app" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  dynamic "ingress" {
    for_each = var.certificate_arn == null ? [] : [443]
    content {
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
  egress {
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "task" {
  name   = "${var.name}-task"
  vpc_id = var.vpc_id
  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_lb" "app" {
  name               = var.name
  load_balancer_type = "application"
  subnets            = var.subnet_ids
  security_groups    = [aws_security_group.alb.id]
}
resource "aws_lb_target_group" "app" {
  name        = var.name
  port        = var.container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check { path = var.health_check_path }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = var.certificate_arn == null ? "forward" : "redirect"
    target_group_arn = var.certificate_arn == null ? aws_lb_target_group.app.arn : null
    dynamic "redirect" {
      for_each = var.certificate_arn == null ? [] : [true]
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}
resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == null ? 0 : 1
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
resource "aws_ecs_task_definition" "app" {
  count                    = var.image_uri == "" ? 0 : 1
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = var.image_uri
    essential    = true
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]
    environment  = [for key, value in var.environment : { name = key, value = value }]
    secrets      = [for key, value in var.secret_arns : { name = key, valueFrom = value }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
  lifecycle {
    precondition {
      condition     = startswith(var.image_uri, "${aws_ecr_repository.app.repository_url}@sha256:")
      error_message = "Deploy a digest from this application's ECR repository."
    }
  }
}
resource "aws_ecs_service" "app" {
  count                              = var.image_uri == "" ? 0 : 1
  name                               = var.name
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app[0].arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  wait_for_steady_state              = true
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = var.assign_public_ip
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = var.container_port
  }
  depends_on = [aws_lb_listener.http, aws_lb_listener.https]
}

output "repository_url" { value = aws_ecr_repository.app.repository_url }
output "cluster_name" { value = aws_ecs_cluster.app.name }
output "service_name" { value = var.name }
output "task_definition_arn" { value = try(aws_ecs_task_definition.app[0].arn, null) }
output "deployed_image" { value = var.image_uri }
output "url" { value = "${var.certificate_arn == null ? "http" : "https"}://${aws_lb.app.dns_name}" }
