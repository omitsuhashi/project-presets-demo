"""Validate containers, deploy immutable image digests and verify ECS revisions."""

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from native import foundation_plan, identity, outputs, run, tf, write_json


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
        print(verify_deployment(target, image))


def verify_deployment(target, image):
    values = outputs(target / "infra/app")
    region = json.loads((target / "infra/foundation/terraform.tfvars.json").read_text())["region"]
    active = run("aws", "ecs", "describe-services", "--region", region, "--cluster", values["cluster_name"],
                 "--services", values["service_name"], "--query", "services[0].taskDefinition", "--output", "text", capture=True)
    if active != values["task_definition_arn"]:
        raise ValueError("ECS did not keep the requested task revision; inspect the deployment rollback/events")
    deployed = run("aws", "ecs", "describe-task-definition", "--region", region, "--task-definition", active,
                   "--query", "taskDefinition.containerDefinitions[?name=='app'].image | [0]", "--output", "text", capture=True)
    if deployed != image:
        raise ValueError("ECS did not keep the requested image; inspect the deployment rollback/events")
    return values["url"]


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
