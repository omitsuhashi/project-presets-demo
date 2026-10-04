"""Copy an initial recipe once, without tracking ownership of generated files."""

import importlib.metadata
import json
import re
from pathlib import Path

from .config import PROFILES, PROVIDER, source, version


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
    text = f'''# Project-owned root. Review module ref/provider updates in your own PR.
terraform {{
  required_version = ">= 1.10, < 2.0"
  required_providers {{
    aws = {{ source = "hashicorp/aws", version = "= {PROVIDER}" }}
  }}
}}
provider "aws" {{
  region = var.region
  default_tags {{ tags = {{ Project = var.name }} }}
}}
'''
    text += "\n" + "\n".join(f'variable "{name}" {{ type = {value} }}' for name, value in inputs.items())
    text += f'\n\nmodule "preset" {{\n  source = "{source(kind, release)}"\n'
    text += "".join(f"  {name} = var.{name}\n" for name in inputs if name != "region") + "}\n\n"
    text += "\n".join(f'output "{name}" {{ value = module.preset.{name} }}' for name in outputs) + "\n"
    return text


def init(target, args):
    release = importlib.metadata.version("project-presets-infra")
    module_release = args.module_version or release
    version(module_release)
    marker = target / "infra/.project-infra.json"
    state = json.loads(marker.read_text()) if marker.exists() else {}
    if args.adopt:
        if args.module_version:
            raise ValueError("--adopt keeps module references; update refs in a separate Terraform PR")
        if not state or not state["release"].startswith("1."):
            raise ValueError("--adopt needs an existing v1 infra/.project-infra.json; preserve state/backends before migration")
        for folder in ["foundation", "app"]:
            if not (target / f"infra/{folder}/preset.tf.json").exists():
                raise ValueError("Keep the v1 Terraform roots in place before --adopt")
    elif state:
        raise ValueError("Infrastructure already exists; maintain project files directly, or use --adopt for v1")
    if args.adopt:
        values = json.loads((target / "infra/foundation/terraform.tfvars.json").read_text())
        for option, key in [("name", "name"), ("repository", "github_repository"), ("region", "region"), ("branch", "github_branch")]:
            supplied = getattr(args, option)
            if supplied is not None and supplied != values[key]:
                raise ValueError("--adopt preserves existing foundation settings; edit them separately after migration")
            setattr(args, option, values[key])
    name = args.name or state.get("name")
    repository = args.repository or state.get("repository")
    region = args.region or state.get("region", "ap-northeast-1")
    branch = args.branch or state.get("branch", "main")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,18}[a-z0-9]", name or ""):
        raise ValueError("--name must be 3-20 lowercase letters/digits/hyphens, starting with a letter")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or ""):
        raise ValueError("--repository requires the consumer's owner/repository")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[1-9][0-9]*", region):
        raise ValueError("Use a commercial AWS region")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", branch):
        raise ValueError("Use a literal default branch, without wildcards")
    application = target / ".project-preset.json"
    configured = json.loads(application.read_text())["profile"] if application.exists() else state.get("profile")
    if args.profile and configured and args.profile != configured:
        raise ValueError("Infrastructure profile must match the existing application preset")
    profile = args.profile or configured
    if profile not in PROFILES:
        raise ValueError("Use typescript-hono or python-fastapi, or specify --profile for an existing app")
    manifest = "package.json" if profile.startswith("typescript-") else "pyproject.toml"
    if not (target / manifest).exists():
        raise ValueError("Run the application preset --setup before infrastructure init")
    recipe = Path(__file__).parent / "recipe"
    files = {f"infra/scripts/{path.name}": path.read_text() for path in (recipe / "scripts").glob("*.py")}
    files["infra/README.md"] = (recipe / "README.md").read_text().replace("__RECIPE_VERSION__", release)
    files[".github/workflows/deploy-infra.yml"] = (recipe / "deploy.yml").read_text().replace("__BRANCH__", json.dumps(branch))
    files[".github/workflows/check-infra.yml"] = (recipe / "check.yml").read_text()
    if not args.adopt:
        port, docker = PROFILES[profile]
        files.update({
            "infra/foundation/main.tf": root("aws-foundation", module_release),
            "infra/app/main.tf": root("aws-container-service", module_release),
            "infra/foundation/terraform.tfvars.json": json.dumps({"name": name, "region": region,
                "github_repository": repository, "github_branch": branch,
                "existing_oidc_provider_arn": None, "secret_arns": {}}, indent=2) + "\n",
            "infra/app/terraform.tfvars.json": json.dumps({"name": name, "region": region,
                "container_port": port, "health_check_path": "/health", "environment": {}, "secret_arns": {},
                "cpu": 256, "memory": 512, "desired_count": 1, "assign_public_ip": True, "certificate_arn": None}, indent=2) + "\n",
        })
        if any((target / f"infra/{folder}").exists() for folder in ["foundation", "app"]):
            raise ValueError("Existing Terraform roots need manual integration; init does not merge infrastructure")
        templates = Path(__file__).parent / "templates"
        for destination, template in [("Dockerfile", f"{docker}.Dockerfile"), (".dockerignore", "dockerignore")]:
            if not (target / destination).exists():
                files[destination] = (templates / template).read_text()
        if profile == "typescript-hono" and not any((target / filename).exists() for filename in ["app.ts", "server.ts"]):
            files["server.ts"] = (templates / "hono-server.ts").read_text()
            files["app.ts"] = (templates / "hono-app.ts").read_text()
        if profile == "python-fastapi" and not (target / "main.py").exists():
            files["main.py"] = (templates / "fastapi-main.py").read_text()
    replace = set()
    remove = target / ".github/workflows/update-infra.yml"
    if args.adopt:
        deploy = target / ".github/workflows/deploy-infra.yml"
        for path, template in [(deploy, "deploy.yml"), (remove, "update.yml")]:
            expected = (recipe / "legacy" / template).read_text().replace("__BRANCH__", json.dumps(branch))
            if path.exists() and path.read_text() != expected:
                raise ValueError(f"Custom workflow needs manual integration: {path}")
        if deploy.exists():
            replace.add(".github/workflows/deploy-infra.yml")
    conflicts = [filename for filename in files if (target / filename).exists() and filename not in replace]
    if conflicts:
        raise ValueError(f"Existing files need integration: {', '.join(conflicts)}")
    for filename, text in files.items():
        destination = target / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if filename in replace:
            destination.write_text(text)
        else:
            with destination.open("x") as file:
                file.write(text)
    with (target / ".gitignore").open("a") as file:
        file.write("\n# Terraform local cache, state and saved plans\n**/.terraform/\n*.tfstate*\n*.tfplan\n*.preset-new\n")
    if args.adopt:
        marker.unlink()
        remove.unlink(missing_ok=True)
    print("Created project-owned infrastructure files. Edit and update them in this repository; see infra/README.md. No AWS resources were changed.")
