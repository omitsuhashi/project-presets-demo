"""Project-owned Terraform and AWS operations; edit alongside your infrastructure."""

import json
import subprocess


def run(*args, directory=None, capture=False, input_text=None, env=None):
    result = subprocess.run(args, cwd=directory, input=input_text, text=True, env=env,
                            stdout=subprocess.PIPE if capture else None, check=True)
    return result.stdout.strip() if capture else None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".preset-new")
    with temporary.open("x") as file:
        file.write(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def tf(path, *args, capture=False):
    return run("terraform", f"-chdir={path}", *args, capture=capture)


def outputs(path):
    return {key: item["value"] for key, item in json.loads(tf(path, "output", "-json", capture=True)).items()}


def backend(path, bucket, region, key):
    write_json(path / "backend.tf.json", {"terraform": {"backend": {"s3": {
        "bucket": bucket, "key": key, "region": region, "encrypt": True,
        "use_lockfile": True, "workspace_key_prefix": "app/workspaces"}}}})


def identity(target):
    region = json.loads((target / "infra/foundation/terraform.tfvars.json").read_text())["region"]
    account = json.loads(run("aws", "sts", "get-caller-identity", "--region", region, "--output", "json", capture=True))["Account"]
    config = target / "infra/aws.json"
    if config.exists() and json.loads(config.read_text())["account"] != account:
        raise ValueError("AWS credentials belong to a different account than infra/aws.json")
    return account


def foundation_plan(target, require_unchanged=False):
    configured = json.loads((target / "infra/app/terraform.tfvars.json").read_text())["secret_arns"]
    allowed = json.loads((target / "infra/foundation/terraform.tfvars.json").read_text())["secret_arns"]
    if configured != allowed:
        raise ValueError("Secret ARN changes need operator review: run bootstrap --apply")
    path = target / "infra/foundation"
    tf(path, "init", "-input=false")
    result = subprocess.run(["terraform", f"-chdir={path}", "plan", "-input=false", "-lock-timeout=5m",
                             "-detailed-exitcode", "-out=foundation.tfplan"])
    if result.returncode not in (0, 2):
        raise ValueError("Foundation plan failed")
    if result.returncode == 2 and require_unchanged:
        raise ValueError("Foundation changes need operator review: run bootstrap --apply before CI deployment")
