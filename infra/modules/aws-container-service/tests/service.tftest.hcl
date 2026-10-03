mock_provider "aws" {
  override_during = plan
  mock_data "aws_region" { defaults = { region = "ap-northeast-1" } }
  mock_resource "aws_ecr_repository" { defaults = { repository_url = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/demo" } }
  mock_resource "aws_lb" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:loadbalancer/app/demo/1234567890123456", dns_name = "demo.example.invalid" } }
  mock_resource "aws_lb_target_group" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/demo/1234567890123456" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:ap-northeast-1:123456789012:task-definition/demo:1" } }
}
variables {
  name               = "demo"
  vpc_id             = "vpc-12345678"
  subnet_ids         = ["subnet-12345678", "subnet-87654321"]
  execution_role_arn = "arn:aws:iam::123456789012:role/demo-execution"
  task_role_arn      = "arn:aws:iam::123456789012:role/demo-task"
  container_port     = 3000
  health_check_path  = "/health"
  image_uri          = ""
}
run "empty_bootstrap" {
  command = plan
  assert {
    condition     = length(aws_ecs_service.app) == 0 && length(aws_ecs_task_definition.app) == 0
    error_message = "Bootstrap must create the repository without attempting to pull an absent image."
  }
}
run "deploy_digest" {
  command = plan
  variables { image_uri = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/demo@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.app[0].container_definitions)[0].image == var.image_uri && aws_ecs_service.app[0].wait_for_steady_state && aws_ecs_service.app[0].deployment_circuit_breaker[0].rollback
    error_message = "Terraform must own the immutable image and wait for a healthy deployment."
  }
  assert {
    condition     = aws_ecr_repository.app.image_tag_mutability == "IMMUTABLE" && aws_ecr_repository.app.force_delete == false && aws_lb_target_group.app.health_check[0].path == "/health"
    error_message = "Preserve images and check the application's health endpoint."
  }
}
run "tls" {
  command = plan
  variables { certificate_arn = "arn:aws:acm:ap-northeast-1:123456789012:certificate/12345678-1234-1234-1234-123456789012" }
  assert {
    condition     = aws_lb_listener.http.default_action[0].type == "redirect" && length(aws_lb_listener.https) == 1 && startswith(output.url, "https://")
    error_message = "Configured TLS must redirect HTTP and serve HTTPS."
  }
}
run "reject_tag" {
  command = plan
  variables { image_uri = "example.invalid/demo:latest" }
  expect_failures = [var.image_uri]
}
run "reject_foreign_repository" {
  command = plan
  variables { image_uri = "example.invalid/demo@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [aws_ecs_task_definition.app]
}
