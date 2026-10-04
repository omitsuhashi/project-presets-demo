"""Generate consumer-owned roots, containers and workflows."""

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from .config import PROFILES, PROVIDER, REPOSITORY, source, version
from .native import write_json


def root(kind, release):
    inputs = ({"name": "string", "github_repository": "string", "github_branch": "string",
               "existing_oidc_provider_arn": "string", "secret_arns": "map(string)"}
              if kind == "aws-foundation" else
              {"name": "string", "vpc_id": "string", "subnet_ids": "list(string)",
               "execution_role_arn": "string", "task_role_arn": "string", "image_uri": "string",
               "container_port": "number", "health_check_path": "string", "environment": "map(string)",
               "secret_arns": "map(string)", "cpu": "number", "memory": "number", "desired_count": "number",
               "assign_public_ip": "bool", "certificate_arn": "string"})
    inputs["region"] = "string"
    outputs = (["state_bucket", "deployment_role_arn", "execution_role_arn", "task_role_arn", "vpc_id", "subnet_ids"]
               if kind == "aws-foundation" else ["repository_url", "deployed_image", "url", "cluster_name", "service_name", "task_definition_arn"])
    return {
        "terraform": {"required_version": ">= 1.10, < 2.0",
                      "required_providers": {"aws": {"source": "hashicorp/aws", "version": f"= {PROVIDER}"}}},
        "provider": {"aws": {"region": "${var.region}", "default_tags": [{"tags": {"Project": "${var.name}"}}]}},
        "variable": {name: {"type": kind} for name, kind in inputs.items()},
        "module": {"preset": {"source": source(kind, release), **{name: "${var." + name + "}" for name in inputs if name != "region"}}},
        "output": {name: {"value": "${module.preset." + name + "}"} for name in outputs},
    }


def init(target, args):
    release = importlib.metadata.version("project-presets-infra")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,18}[a-z0-9]", args.name or ""):
        raise ValueError("--name must be 3-20 lowercase letters/digits/hyphens, starting with a letter")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository or ""):
        raise ValueError("--repository requires the consumer's owner/repository")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[1-9][0-9]*", args.region):
        raise ValueError("Use a commercial AWS region")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", args.branch):
        raise ValueError("Use a literal default branch, without wildcards")
    application = target / ".project-preset.json"
    if args.profile is None and not application.exists():
        raise ValueError("Run an application preset --setup first, or use --profile with an existing app")
    configured = json.loads(application.read_text())["profile"] if application.exists() else None
    if args.profile and configured and args.profile != configured:
        raise ValueError("Infrastructure profile must match the existing application preset")
    profile = args.profile or configured
    if profile not in PROFILES:
        raise ValueError("The first deployment demo supports typescript-hono and python-fastapi")
    manifest = "package.json" if profile.startswith("typescript-") else "pyproject.toml"
    if not (target / manifest).exists():
        raise ValueError("Run the application preset --setup before infrastructure init")
    marker = target / "infra/.project-infra.json"
    if marker.exists():
        raise ValueError("Infrastructure already exists; use check, update, or the existing configuration")
    port, docker = PROFILES[profile]
    files = {
        "infra/foundation/preset.tf.json": json.dumps(root("aws-foundation", release), indent=2) + "\n",
        "infra/app/preset.tf.json": json.dumps(root("aws-container-service", release), indent=2) + "\n",
        "infra/foundation/terraform.tfvars.json": json.dumps({"name": args.name, "region": args.region,
            "github_repository": args.repository, "github_branch": args.branch,
            "existing_oidc_provider_arn": None, "secret_arns": {}}, indent=2) + "\n",
        "infra/app/terraform.tfvars.json": json.dumps({"name": args.name, "region": args.region,
            "container_port": port, "health_check_path": "/health", "environment": {}, "secret_arns": {},
            "cpu": 256, "memory": 512, "desired_count": 1, "assign_public_ip": True, "certificate_arn": None}, indent=2) + "\n",
        ".github/workflows/deploy-infra.yml": workflow("Deploy AWS app", "infra-deploy.yml", args.branch, release),
        ".github/workflows/update-infra.yml": workflow("Update AWS infrastructure", "infra-update.yml", args.branch, release),
    }
    templates = Path(__file__).parent / "templates"
    for name, template in [("Dockerfile", f"{docker}.Dockerfile"), (".dockerignore", "dockerignore")]:
        if not (target / name).exists():
            files[name] = (templates / template).read_text()
    if profile == "typescript-hono" and not any((target / name).exists() for name in ["app.ts", "server.ts"]):
        files["server.ts"] = (templates / "hono-server.ts").read_text()
        files["app.ts"] = (templates / "hono-app.ts").read_text()
    if profile == "python-fastapi" and not (target / "main.py").exists():
        files["main.py"] = (templates / "fastapi-main.py").read_text()
    conflicts = [name for name in files if (target / name).exists()]
    if conflicts:
        raise ValueError(f"Existing files need integration: {', '.join(conflicts)}")
    hashes = {name: hashlib.sha256(files[name].encode()).hexdigest() for name in ["Dockerfile", ".dockerignore"] if name in files}
    for name, text in files.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as file:
            file.write(text)
    ignore = target / ".gitignore"
    lines = "\n# Terraform local cache, state, credentials and saved plans\n**/.terraform/\n*.tfstate*\n*.tfplan\n*.preset-new\n"
    with ignore.open("a") as file:
        file.write(lines)
    write_json(marker, {"release": release, "profile": profile, "name": args.name,
                        "repository": args.repository, "branch": args.branch, "region": args.region, "provider": PROVIDER, "files": hashes})
    print("Created Terraform calls, Dockerfile and deployment/update workflows. AWS authentication and bootstrap can be configured later.")


def workflow(name, called, branch, release):
    trigger = f"  push:\n    branches: [{json.dumps(branch)}]\n" if called == "infra-deploy.yml" else "  schedule:\n    - cron: '45 2 * * 1'\n"
    return f"""name: {name}
on:
{trigger}  workflow_dispatch:
permissions:
  contents: {'write' if called == 'infra-update.yml' else 'read'}
  pull-requests: {'write' if called == 'infra-update.yml' else 'read'}
  id-token: write
concurrency:
  group: aws-infrastructure
  cancel-in-progress: false
jobs:
  infrastructure:
    uses: {REPOSITORY}/.github/workflows/infra-consumer.yml@infra-tools/v{version(release)[0]}
    with:
      mode: {'update' if called == 'infra-update.yml' else 'deploy'}
"""
