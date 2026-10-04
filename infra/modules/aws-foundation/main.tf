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
    error_message = "Use a 3-20 character application name."
  }
}
variable "github_repository" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use owner/repository."
  }
}
variable "github_branch" {
  type    = string
  default = "main"
  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+$", var.github_branch))
    error_message = "Use a literal branch name; wildcard trust is not supported."
  }
}
variable "existing_oidc_provider_arn" {
  type    = string
  default = null
}
variable "secret_arns" {
  type    = map(string)
  default = {}
  validation {
    condition     = alltrue([for arn in values(var.secret_arns) : can(regex("^arn:aws:(secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+|ssm:[a-z0-9-]+:[0-9]{12}:parameter/[A-Za-z0-9_./-]+)$", arn))])
    error_message = "Use literal Secrets Manager or SSM parameter ARNs; wildcard permissions and secret values are not supported."
  }
}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_availability_zones" "available" { state = "available" }
locals {
  prefix = "arn:aws"
  scope  = "${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"
  bucket = "${var.name}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.region}-tfstate"
  ecr    = "${local.prefix}:ecr:${local.scope}:repository/${var.name}"
  logs   = "${local.prefix}:logs:${local.scope}:log-group:/project-presets/${var.name}"
}

# ponytail: demo network uses two public subnets without NAT; bring private subnets to the service module for production.
resource "aws_vpc" "app" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
resource "aws_subnet" "app" {
  count             = 2
  vpc_id            = aws_vpc.app.id
  cidr_block        = cidrsubnet(aws_vpc.app.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
}
resource "aws_internet_gateway" "app" { vpc_id = aws_vpc.app.id }
resource "aws_route_table" "app" {
  vpc_id = aws_vpc.app.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app.id
  }
}
resource "aws_route_table_association" "app" {
  count          = 2
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app.id
}
resource "aws_s3_bucket" "state" {
  bucket        = local.bucket
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.existing_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "deployment" {
  name = "${var.name}-deployment"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = var.existing_oidc_provider_arn == null ? aws_iam_openid_connect_provider.github[0].arn : var.existing_oidc_provider_arn }
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:ref:refs/heads/${var.github_branch}"
      } }
    }]
  })
}
resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }] })
}
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = aws_iam_role.execution.assume_role_policy
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = local.ecr },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${local.logs}:*" }
    ], length(var.secret_arns) == 0 ? [] : [{
      Effect = "Allow", Action = ["secretsmanager:GetSecretValue", "ssm:GetParameters"], Resource = values(var.secret_arns)
  }]) })
}
resource "aws_iam_role_policy" "deployment" {
  role = aws_iam_role.deployment.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken", "ecs:Describe*", "ecs:List*", "ec2:Describe*", "elasticloadbalancing:Describe*", "logs:DescribeLogGroups"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:*"], Resource = local.ecr },
    { Effect = "Allow", Action = ["ecs:*"], Resource = ["${local.prefix}:ecs:${local.scope}:cluster/${var.name}", "${local.prefix}:ecs:${local.scope}:service/${var.name}/${var.name}", "${local.prefix}:ecs:${local.scope}:task-definition/${var.name}:*", "${local.prefix}:ecs:${local.scope}:task/${var.name}/*"] },
    { Effect = "Allow", Action = ["logs:*"], Resource = [local.logs, "${local.logs}:*"] },
    { Effect = "Allow", Action = ["elasticloadbalancing:*"], Resource = ["${local.prefix}:elasticloadbalancing:${local.scope}:loadbalancer/app/${var.name}/*", "${local.prefix}:elasticloadbalancing:${local.scope}:targetgroup/${var.name}/*", "${local.prefix}:elasticloadbalancing:${local.scope}:listener/app/${var.name}/*/*", "${local.prefix}:elasticloadbalancing:${local.scope}:listener-rule/app/${var.name}/*/*/*"] },
    { Effect = "Allow", Action = ["ec2:CreateSecurityGroup"], Resource = aws_vpc.app.arn },
    { Effect = "Allow", Action = ["ec2:CreateSecurityGroup", "ec2:CreateTags"], Resource = "${local.prefix}:ec2:${local.scope}:security-group/*", Condition = { StringEquals = { "aws:RequestTag/Project" = var.name } } },
    { Effect = "Allow", Action = ["ec2:CreateTags", "ec2:DeleteTags"], Resource = "${local.prefix}:ec2:${local.scope}:security-group/*", Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.name } } },
    { Effect = "Allow", Action = ["ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress", "ec2:DeleteSecurityGroup"], Resource = "${local.prefix}:ec2:${local.scope}:security-group/*", Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.name } } },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.execution.arn, aws_iam_role.task.arn], Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } },
    { Effect = "Allow", Action = ["iam:CreateServiceLinkedRole"], Resource = "${local.prefix}:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*", Condition = { StringEquals = { "iam:AWSServiceName" = ["ecs.amazonaws.com", "elasticloadbalancing.amazonaws.com"] } } },
    # CI can refresh/plan the foundation, but cannot write IAM, networking or foundation state.
    { Effect = "Allow", Action = ["iam:GetRole", "iam:ListRolePolicies", "iam:GetRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:ListInstanceProfilesForRole"], Resource = [aws_iam_role.deployment.arn, aws_iam_role.execution.arn, aws_iam_role.task.arn] },
    { Effect = "Allow", Action = ["iam:GetOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags"], Resource = "${local.prefix}:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com" },
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:Get*"], Resource = aws_s3_bucket.state.arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.state.arn}/foundation/terraform.tfstate" },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.state.arn}/foundation/terraform.tfstate.tflock" },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.state.arn}/app/*" },
    { Effect = "Allow", Action = ["s3:DeleteObject"], Resource = "${aws_s3_bucket.state.arn}/app/*.tflock" }
  ] })
}
output "state_bucket" { value = aws_s3_bucket.state.bucket }
output "deployment_role_arn" { value = aws_iam_role.deployment.arn }
output "execution_role_arn" { value = aws_iam_role.execution.arn }
output "task_role_arn" { value = aws_iam_role.task.arn }
output "vpc_id" { value = aws_vpc.app.id }
output "subnet_ids" { value = aws_subnet.app[*].id }
