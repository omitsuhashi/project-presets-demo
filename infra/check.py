"""Credential-free checks of the shipped CLI, consumer preservation and containers."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import project_presets_infra as preset

ROOT = Path(__file__).resolve().parent.parent
APP_RELEASE = "2.1.0"
RELEASES = f"https://github.com/{preset.REPOSITORY}/releases/download"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def check(containers):
    with tempfile.TemporaryDirectory(prefix="infra-check-") as directory:
        temporary = Path(directory)
        run("uv", "build", "--project", ROOT / "infra", "--out-dir", temporary / "dist")
        wheel = next((temporary / "dist").glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            assert any(name.endswith("templates/hono.Dockerfile") for name in archive.namelist())
        cli = ["uvx", "--python", "3.12", "--from", str(wheel), "project-presets-infra"]
        for profile in preset.PROFILES:
            consumer = temporary / profile
            consumer.mkdir()
            if containers:
                if profile.startswith("typescript-"):
                    run("npx", "--yes", "--allow-remote=root", "--ignore-scripts",
                        f"{RELEASES}/v{APP_RELEASE}/project-presets-demo-{APP_RELEASE}.tgz", profile, consumer, "--setup")
                else:
                    run("uvx", "--python", "3.12", "--from",
                        f"{RELEASES}/v{APP_RELEASE}/project_presets_demo-{APP_RELEASE}-py3-none-any.whl",
                        "project-presets-python", profile, consumer, "--setup")
            else:
                (consumer / ("package.json" if profile.startswith("typescript-") else "pyproject.toml")).write_text("{}")
                preset.write_json(consumer / ".project-preset.json", {"profile": profile})
            run(*cli, "init", "--directory", consumer, "--name", "demo", "--repository", "example/consumer")
            assert "infra-tools/v1" in (consumer / ".github/workflows/update-infra.yml").read_text()
            marker = consumer / "infra/.project-infra.json"
            state = json.loads(marker.read_text())
            # Simulate a managed Docker template from an older release.
            old_docker = consumer / "Dockerfile"
            old_docker.write_text("# old preset\n" + old_docker.read_text())
            state["files"]["Dockerfile"] = hashlib.sha256(old_docker.read_bytes()).hexdigest()
            preset.write_json(marker, state)
            before = marker.read_bytes()
            foundation_before = (consumer / "infra/foundation/preset.tf.json").read_bytes()
            # A foundation/provider conflict must stop before any managed file is replaced.
            app = consumer / "infra/app/preset.tf.json"
            value = json.loads(app.read_text())
            value["resource"] = {"terraform_data": {"custom": {"input": "keep me"}}}
            value["terraform"]["required_providers"]["aws"]["version"] = "custom"
            preset.write_json(app, value)
            with patch.object(preset.importlib.metadata, "version", return_value="1.1.0"):
                try:
                    preset.update(consumer, "1.1.0")
                    raise AssertionError("Managed provider conflict was silently overwritten")
                except ValueError as error:
                    assert "changed locally" in str(error)
                assert marker.read_bytes() == before
                assert (consumer / "infra/foundation/preset.tf.json").read_bytes() == foundation_before
                value["terraform"]["required_providers"]["aws"]["version"] = f"= {preset.PROVIDER}"
                preset.write_json(app, value)
                inputs = consumer / "infra/app/terraform.tfvars.json"
                configured = json.loads(inputs.read_text())
                configured["environment"] = {"CUSTOM": "preserve"}
                preset.write_json(inputs, configured)
                input_bytes = inputs.read_bytes()
                preset.update(consumer, "1.1.0")
                assert json.loads(app.read_text())["resource"] == value["resource"]
                assert inputs.read_bytes() == input_bytes
                assert not old_docker.read_text().startswith("# old preset")
                assert json.loads(app.read_text())["module"]["preset"]["source"].endswith("infra-aws-container-v1.1.0")
            # Exercise bootstrap and plan sequencing through recorded native calls, without AWS.
            operator = temporary / (profile + "-operator")
            shutil.copytree(consumer / "infra", operator / "infra")
            image = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/demo@sha256:" + "a" * 64
            values = {"state_bucket": "demo-state", "deployment_role_arn": "arn:aws:iam::123456789012:role/demo-deployment",
                      "execution_role_arn": "arn:aws:iam::123456789012:role/demo-execution",
                      "task_role_arn": "arn:aws:iam::123456789012:role/demo-task", "vpc_id": "vpc-12345678", "subnet_ids": ["subnet-a", "subnet-b"]}
            with patch.object(preset, "identity", return_value="123456789012"), patch.object(preset.shutil, "which", return_value="/fake"), patch.object(preset, "tf") as native, patch.object(preset, "outputs", side_effect=[values, {"deployed_image": image}]), patch.object(preset.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")):
                preset.bootstrap(operator, True)
                assert any("-migrate-state" in call.args for call in native.call_args_list)
                assert any(f"-var=image_uri={image}" in call.args for call in native.call_args_list)
            with patch.object(preset, "tf") as native, patch.object(preset, "outputs", return_value={"deployed_image": image}):
                preset.plan(operator)
                assert any(f"-var=image_uri={image}" in call.args for call in native.call_args_list)
                assert all("apply" not in call.args for call in native.call_args_list)
            with patch.object(preset, "tf"), patch.object(preset.subprocess, "run", return_value=SimpleNamespace(returncode=2)):
                try:
                    preset.foundation_plan(operator, require_unchanged=True)
                    raise AssertionError("CI would apply an unreviewed IAM/network change")
                except ValueError as error:
                    assert "operator review" in str(error)
            # Validate generated roots against this checkout before its first Git tag exists.
            for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
                path = consumer / "infra" / folder
                value = json.loads((path / "preset.tf.json").read_text())
                value["module"]["preset"]["source"] = str(ROOT / "infra/modules" / kind)
                preset.write_json(path / "preset.tf.json", value)
                run("terraform", f"-chdir={path}", "init", "-backend=false", "-input=false")
                run("terraform", f"-chdir={path}", "validate")
            # init preserves project-owned Dockerfiles and refuses other file collisions.
            existing = temporary / (profile + "-existing")
            existing.mkdir()
            shutil.copy2(consumer / ("package.json" if profile.startswith("typescript-") else "pyproject.toml"), existing)
            (existing / "Dockerfile").write_text("custom Dockerfile\n")
            run(*cli, "init", "--directory", existing, "--profile", profile, "--name", "demo", "--repository", "example/consumer")
            assert (existing / "Dockerfile").read_text() == "custom Dockerfile\n"
            result = subprocess.run([*cli, "bootstrap", "--directory", str(existing)], capture_output=True, text=True)
            assert result.returncode == 1 and "bootstrap --apply" in result.stderr
            if containers:
                run(*cli, "container-check", "--directory", consumer)
        print("Infrastructure wheel, both consumer roots, conflict preservation and deferred bootstrap passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--containers", action="store_true")
    check(parser.parse_args().containers)
