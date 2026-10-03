mock_provider "aws" {
  override_during = plan
  mock_data "aws_region" { defaults = { region = "ap-northeast-1" } }
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_availability_zones" { defaults = { names = ["ap-northeast-1a", "ap-northeast-1c"] } }
  mock_resource "aws_vpc" { defaults = { arn = "arn:aws:ec2:ap-northeast-1:123456789012:vpc/vpc-12345678" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::demo-123456789012-ap-northeast-1-tfstate" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/demo" } }
  mock_resource "aws_iam_openid_connect_provider" { defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" } }
}
variables {
  name              = "demo"
  github_repository = "example/consumer"
}
run "scoped_foundation" {
  command = plan
  assert {
    condition     = jsondecode(aws_iam_role.deployment.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:example/consumer:ref:refs/heads/main"
    error_message = "Only the specified consumer default branch may assume the deployment role."
  }
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled" && aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket.state.force_destroy == false
    error_message = "State must be versioned, private and protected from automatic deletion."
  }
  assert {
    condition     = alltrue([for statement in jsondecode(aws_iam_role_policy.deployment.policy).Statement : alltrue([for action in statement.Action : !contains(["iam:*", "iam:PutRolePolicy", "iam:CreateRole", "ec2:CreateVpc"], action)])])
    error_message = "Routine CI must not modify its IAM permissions or create a VPC."
  }
}
run "reuse_oidc" {
  command = plan
  variables { existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "An existing account OIDC provider must not be adopted or deleted."
  }
}
run "reject_wildcard_trust" {
  command = plan
  variables { github_branch = "*" }
  expect_failures = [var.github_branch]
}
run "reject_wildcard_secret_permissions" {
  command = plan
  variables { secret_arns = { TOKEN = "*" } }
  expect_failures = [var.secret_arns]
}
