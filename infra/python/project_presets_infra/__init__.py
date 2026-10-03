"""Bootstrap and deploy a consumer through versioned AWS Terraform modules."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPOSITORY = "omitsuhashi/project-presets-demo"
PREFIX = "infra-aws-container-v"
PROVIDER = "6.67.0"
PROFILES = {"typescript-hono": (3000, "hono"), "python-fastapi": (8000, "fastapi")}


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


def version(value):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Use a stable infrastructure version, for example 1.0.0")
    return tuple(map(int, value.split(".")))


def source(kind, release):
    version(release)
    return f"git::https://github.com/{REPOSITORY}.git//infra/modules/{kind}?ref={PREFIX}{release}"


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
               if kind == "aws-foundation" else ["repository_url", "deployed_image", "url", "cluster_name", "service_name"])
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
    profile = args.profile or json.loads(application.read_text())["profile"]
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


def tf(path, *args, capture=False):
    return run("terraform", f"-chdir={path}", *args, capture=capture)


def outputs(path):
    return {key: item["value"] for key, item in json.loads(tf(path, "output", "-json", capture=True)).items()}


def backend(path, bucket, region, key):
    write_json(path / "backend.tf.json", {"terraform": {"backend": {"s3": {
        "bucket": bucket, "key": key, "region": region, "encrypt": True,
        "use_lockfile": True, "workspace_key_prefix": "app/workspaces"}}}})


def identity(target):
    region = json.loads((target / "infra/.project-infra.json").read_text())["region"]
    account = json.loads(run("aws", "sts", "get-caller-identity", "--region", region, "--output", "json", capture=True))["Account"]
    config = target / "infra/aws.json"
    if config.exists() and json.loads(config.read_text())["account"] != account:
        raise ValueError("AWS credentials belong to a different account than infra/aws.json")
    return account


def bootstrap(target, apply):
    if not apply:
        raise ValueError("bootstrap creates AWS resources; run bootstrap --apply when operator credentials are ready")
    foundation, app = target / "infra/foundation", target / "infra/app"
    if not shutil.which("aws") or not shutil.which("terraform"):
        raise ValueError("bootstrap needs Terraform >=1.10 and AWS CLI with operator credentials")
    account = identity(target)
    state = json.loads((target / "infra/.project-infra.json").read_text())
    variables = json.loads((foundation / "terraform.tfvars.json").read_text())
    variables["secret_arns"] = json.loads((app / "terraform.tfvars.json").read_text())["secret_arns"]
    tf(foundation, "init", "-input=false", "-migrate-state", "-force-copy")
    listed = subprocess.run(["terraform", f"-chdir={foundation}", "state", "list"], capture_output=True, text=True)
    if listed.returncode and "No state file was found" not in listed.stderr:
        raise ValueError(listed.stderr)
    # Reuse an account's OIDC provider; don't adopt or delete another project's provider.
    if "aws_iam_openid_connect_provider.github" not in listed.stdout and variables["existing_oidc_provider_arn"] is None:
        arn = f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
        result = subprocess.run(["aws", "iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", arn], capture_output=True, text=True)
        if result.returncode == 0:
            variables["existing_oidc_provider_arn"] = arn
        elif "NoSuchEntity" not in result.stderr:
            raise ValueError(result.stderr)
    write_json(foundation / "terraform.tfvars.json", variables)
    tf(foundation, "init", "-input=false")
    tf(foundation, "plan", "-input=false", "-out=bootstrap.tfplan")
    # --apply explicitly authorizes applying the displayed, saved plan.
    tf(foundation, "apply", "bootstrap.tfplan")
    values = outputs(foundation)
    if not (foundation / "backend.tf.json").exists():
        backend(foundation, values["state_bucket"], state["region"], "foundation/terraform.tfstate")
        tf(foundation, "init", "-migrate-state", "-force-copy", "-input=false")
    inputs = {key: values[key] for key in ["vpc_id", "subnet_ids", "execution_role_arn", "task_role_arn"]}
    generated = app / "foundation.auto.tfvars.json"
    existing = json.loads(generated.read_text()) if generated.exists() else {}
    write_json(generated, {**existing, **inputs})
    backend(app, values["state_bucket"], state["region"], "app/terraform.tfstate")
    deployment_role = values["deployment_role_arn"]
    tf(app, "init", "-input=false")
    values = outputs(app)
    image = values.get("deployed_image", "")
    tf(app, "plan", "-input=false", f"-var=image_uri={image}", "-out=bootstrap.tfplan")
    tf(app, "apply", "bootstrap.tfplan")
    write_json(target / "infra/aws.json", {"account": account, "region": state["region"], "role": deployment_role})
    print("Bootstrap complete. Commit infra/*.json, root calls, native provider locks and workflows. Never commit state/plans or AWS credentials.")


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


def plan(target, image=None, apply=False):
    app = target / "infra/app"
    if not (app / "backend.tf.json").exists():
        raise ValueError("Run bootstrap after AWS authentication; no resources are created by init")
    tf(app, "init", "-input=false")
    if image is None:
        image = outputs(app).get("deployed_image")
        if not image:
            raise ValueError("No app image is deployed yet; run deploy first")
    tf(app, "plan", "-input=false", f"-var=image_uri={image}", "-lock-timeout=5m", "-out=deployment.tfplan")
    if apply:
        tf(app, "apply", "-input=false", "deployment.tfplan")
        values = outputs(app)
        region = json.loads((target / "infra/.project-infra.json").read_text())["region"]
        active = run("aws", "ecs", "describe-services", "--region", region, "--cluster", values["cluster_name"],
                     "--services", values["service_name"], "--query", "services[0].taskDefinition", "--output", "text", capture=True)
        deployed = run("aws", "ecs", "describe-task-definition", "--region", region, "--task-definition", active,
                       "--query", "taskDefinition.containerDefinitions[?name=='app'].image | [0]", "--output", "text", capture=True)
        if deployed != image:
            raise ValueError("ECS did not keep the requested image; inspect the deployment rollback/events")
        print(values["url"])


def container_check(target, image=None):
    variables = json.loads((target / "infra/app/terraform.tfvars.json").read_text())
    built = image is None
    image = image or f"preset-check:{uuid.uuid4().hex}"
    if built:
        run("docker", "build", "--platform", "linux/amd64", "--tag", image, ".", directory=target)
    if variables["secret_arns"]:
        # AWS secrets stay in ECS; the deployment's ALB/steady-state checks verify startup there.
        if built:
            run("docker", "image", "rm", image)
        print("Container build passed; AWS secret-dependent health is checked by ECS/ALB during deployment")
        return
    environment = [f"--env={key}={value}" for key, value in variables["environment"].items()]
    container = run("docker", "run", "--detach", *environment, "--publish", f"127.0.0.1::{variables['container_port']}", image, capture=True)
    try:
        port = run("docker", "port", container, str(variables["container_port"]), capture=True).split(":")[-1]
        url = f"http://127.0.0.1:{port}{variables['health_check_path']}"
        for _attempt in range(60):
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        print("Container health check passed")
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        run("docker", "logs", container)
        raise ValueError("Container health endpoint did not return HTTP 200")
    finally:
        run("docker", "rm", "--force", container)
        if built:
            run("docker", "image", "rm", image)


def deploy(target):
    config = json.loads((target / "infra/aws.json").read_text())
    identity(target)
    foundation_plan(target, require_unchanged=True)
    app = target / "infra/app"
    tf(app, "init", "-input=false")
    repository = outputs(app)["repository_url"]
    tag = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex) + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    image = f"{repository}:build-{tag}"
    token = run("aws", "ecr", "get-login-password", "--region", config["region"], capture=True)
    with tempfile.TemporaryDirectory(prefix="preset-docker-") as credentials:
        # Keep the configured Docker engine/context while isolating registry credentials.
        configured = Path(os.environ.get("DOCKER_CONFIG", Path.home() / ".docker"))
        config_file = configured / "config.json"
        if config_file.exists():
            settings = json.loads(config_file.read_text())
            write_json(Path(credentials) / "config.json", {key: value for key, value in settings.items()
                       if key not in {"auths", "credsStore", "credHelpers"}})
        for folder in ["contexts", "cli-plugins"]:
            if (configured / folder).exists():
                (Path(credentials) / folder).symlink_to(configured / folder, target_is_directory=True)
        env = {**os.environ, "DOCKER_CONFIG": credentials}
        run("docker", "login", "--username", "AWS", "--password-stdin", repository.split("/")[0], input_text=token, env=env)
        run("docker", "build", "--platform", "linux/amd64", "--tag", image, ".", directory=target, env=env)
        container_check(target, image)
        run("docker", "push", image, env=env)
    digest = run("aws", "ecr", "describe-images", "--region", config["region"], "--repository-name",
                 repository.split("/", 1)[1], "--image-ids", f"imageTag=build-{tag}", "--query", "imageDetails[0].imageDigest", "--output", "text", capture=True)
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("ECR did not return an immutable image digest")
    plan(target, image=f"{repository}@{digest}", apply=True)


def update(target, requested):
    marker = target / "infra/.project-infra.json"
    state = json.loads(marker.read_text())
    current = version(state["release"])
    selected = requested
    if not selected:
        tags = run("gh", "api", f"repos/{REPOSITORY}/releases", "--paginate", "--jq",
                   ".[] | select(.draft == false and .prerelease == false) | .tag_name", capture=True).splitlines()
        available = [tag[len(PREFIX):] for tag in tags if tag.startswith(PREFIX) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", tag[len(PREFIX):])]
        available = [item for item in available if version(item)[0] == current[0] and version(item) >= current]
        if not available:
            raise ValueError("No compatible infrastructure release exists")
        selected = max(available, key=version)
    if version(selected)[0] != current[0]:
        raise ValueError("Major infrastructure upgrades need an explicit root/module migration")
    if selected != importlib.metadata.version("project-presets-infra"):
        raise ValueError("Execute the infrastructure CLI from the selected release so tooling and provider pins match")
    pending = []
    for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
        path = target / f"infra/{folder}/preset.tf.json"
        value = json.loads(path.read_text())
        reference = value["module"]["preset"]["source"]
        if reference not in {source(kind, state["release"]), source(kind, selected)}:
            raise ValueError(f"{folder}'s managed module reference was changed locally")
        value["module"]["preset"]["source"] = source(kind, selected)
        provider = value["terraform"]["required_providers"]["aws"]
        if provider.get("source") != "hashicorp/aws" or provider.get("version") not in {f"= {state['provider']}", f"= {PROVIDER}"}:
            raise ValueError(f"{folder}'s managed provider pin was changed locally")
        provider["version"] = f"= {PROVIDER}"
        pending.append((path, value))
    if not set(state["files"]).issubset({"Dockerfile", ".dockerignore"}):
        raise ValueError("Unsupported managed file in infrastructure marker")
    hashes, copied = {}, []
    templates = Path(__file__).parent / "templates"
    docker = PROFILES[state["profile"]][1]
    for name, digest in state["files"].items():
        path = target / name
        content = (templates / (f"{docker}.Dockerfile" if name == "Dockerfile" else "dockerignore")).read_bytes()
        new_digest = hashlib.sha256(content).hexdigest()
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() not in {digest, new_digest}:
            raise ValueError(f"{name} was changed or deleted locally; resolve before updating")
        hashes[name] = new_digest
        copied.append((path, content))
    for path, value in pending:
        write_json(path, value)
    for path, content in copied:
        temporary = path.with_name(path.name + ".preset-new")
        with temporary.open("xb") as file:
            file.write(content)
        temporary.replace(path)
    write_json(marker, {**state, "release": selected, "provider": PROVIDER, "files": hashes})
    print(f"Updated infrastructure {state['release']} -> {selected}; review both Terraform plans before applying")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "check", "container-check", "bootstrap", "plan", "deploy", "update"])
    parser.add_argument("--directory", default=".")
    parser.add_argument("--name")
    parser.add_argument("--repository")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--version")
    parser.add_argument("--apply", action="store_true", help="Authorize AWS resource creation during bootstrap")
    args = parser.parse_args()
    target = Path(args.directory).resolve()
    try:
        if args.command == "init":
            init(target, args)
        elif args.command == "bootstrap":
            bootstrap(target, args.apply)
        elif args.command == "container-check":
            container_check(target)
        elif args.command == "deploy":
            deploy(target)
        elif args.command == "plan":
            identity(target)
            foundation_plan(target)
            plan(target)
        elif args.command == "update":
            update(target, args.version)
        else:
            state = json.loads((target / "infra/.project-infra.json").read_text())
            for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
                path = target / f"infra/{folder}"
                value = json.loads((path / "preset.tf.json").read_text())
                if value["module"]["preset"]["source"] != source(kind, state["release"]):
                    raise ValueError("Apply the pinned module reference")
                provider = value["terraform"]["required_providers"]["aws"]
                if provider.get("source") != "hashicorp/aws" or provider.get("version") != f"= {state['provider']}":
                    raise ValueError("Apply the managed provider pin")
                tf(path, "init", "-upgrade", "-backend=false", "-input=false")
                tf(path, "validate")
    except (OSError, ValueError, KeyError, AssertionError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
