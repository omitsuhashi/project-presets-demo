"""Credential-free checks of initial scaffolding, consumer ownership and AWS helpers."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_presets_infra.config import PROFILES, REPOSITORY

ROOT = Path(__file__).resolve().parent.parent
APP_RELEASE = "2.1.0"
RELEASES = f"https://github.com/{REPOSITORY}/releases/download"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def snapshot(path):
    return {str(file.relative_to(path)): file.read_bytes() for file in path.rglob("*") if file.is_file()}


def check(containers):
    with tempfile.TemporaryDirectory(prefix="infra-check-") as directory:
        temporary = Path(directory)
        run("uv", "build", "--project", ROOT / "infra", "--out-dir", temporary / "dist")
        wheel = next((temporary / "dist").glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            for suffix in ["templates/hono.Dockerfile", "recipe/scripts/infra.py", "recipe/deploy.yml", "recipe/check.yml", "recipe/README.md"]:
                assert any(name.endswith(suffix) for name in archive.namelist()), suffix
        cli = ["uvx", "--python", "3.12", "--from", str(wheel), "project-presets-infra"]
        for profile in PROFILES:
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
                (consumer / ".project-preset.json").write_text(json.dumps({"profile": profile}))
            run(*cli, "init", "--directory", consumer, "--name", "demo", "--repository", "example/consumer")
            assert not (consumer / "infra/.project-infra.json").exists()
            assert not (consumer / ".github/workflows/update-infra.yml").exists()
            deploy_workflow = (consumer / ".github/workflows/deploy-infra.yml").read_text()
            assert "python3 infra/scripts/infra.py deploy" in deploy_workflow
            assert "infra-tools/" not in deploy_workflow and "path: provider" not in deploy_workflow
            assert (consumer / ".github/workflows/check-infra.yml").exists()
            assert "2.0.0" in (consumer / "infra/README.md").read_text()
            sys.path.insert(0, str(consumer / "infra/scripts"))
            import bootstrap
            import deploy
            import native
            # Consumer changes are ordinary source changes, with no managed hash/pin check.
            docker = consumer / "Dockerfile"
            docker.write_text("# consumer-owned\n" + docker.read_text())
            (consumer / "infra/app/main.tf").write_text((consumer / "infra/app/main.tf").read_text() + '\nresource "terraform_data" "custom" { input = "keep me" }\n')
            inputs = consumer / "infra/app/terraform.tfvars.json"
            configured = json.loads(inputs.read_text())
            configured["environment"] = {"CUSTOM": "preserve"}
            native.write_json(inputs, configured)
            before = snapshot(consumer)
            result = subprocess.run([*cli, "init", "--directory", str(consumer), "--name", "demo", "--repository", "example/consumer"], capture_output=True, text=True)
            assert result.returncode == 1 and "manual integration" in result.stderr
            assert snapshot(consumer) == before
            result = subprocess.run([*cli, "update", "--directory", str(consumer)], capture_output=True, text=True)
            assert result.returncode == 2 and snapshot(consumer) == before
            # Scripts run from the consumer, even when the scaffolding package is absent.
            operator = temporary / (profile + "-operator")
            shutil.copytree(consumer / "infra", operator / "infra")
            result = subprocess.run([sys.executable, str(operator / "infra/scripts/infra.py"), "bootstrap"], cwd=temporary, capture_output=True, text=True)
            assert result.returncode == 1 and "bootstrap --apply" in result.stderr
            image = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/demo@sha256:" + "a" * 64
            values = {"state_bucket": "demo-state", "deployment_role_arn": "arn:aws:iam::123456789012:role/demo-deployment",
                      "execution_role_arn": "arn:aws:iam::123456789012:role/demo-execution", "task_role_arn": "arn:aws:iam::123456789012:role/demo-task",
                      "vpc_id": "vpc-12345678", "subnet_ids": ["subnet-a", "subnet-b"]}
            with patch.object(bootstrap, "identity", return_value="123456789012"), patch.object(bootstrap.shutil, "which", return_value="/fake"), patch.object(bootstrap, "tf") as commands, patch.object(bootstrap, "outputs", side_effect=[values, {"deployed_image": image}]), patch.object(bootstrap, "verify_deployment") as verify, patch.object(bootstrap.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="module.preset.aws_iam_openid_connect_provider.github[0]\n", stderr="")) as aws:
                bootstrap.bootstrap(operator, True)
                verify.assert_called_once_with(operator, image)
                assert any("-migrate-state" in call.args for call in commands.call_args_list)
                assert any(f"-var=image_uri={image}" in call.args for call in commands.call_args_list)
                assert not any("get-open-id-connect-provider" in call.args[0] for call in aws.call_args_list)
                assert json.loads((operator / "infra/foundation/terraform.tfvars.json").read_text())["existing_oidc_provider_arn"] is None
            # A customized backend must not be overwritten on bootstrap retry.
            app_backend = operator / "infra/app/backend.tf.json"
            custom_backend = app_backend.read_text().replace("app/terraform.tfstate", "custom/production.tfstate")
            app_backend.write_text(custom_backend)
            with patch.object(bootstrap, "identity", return_value="123456789012"), patch.object(bootstrap.shutil, "which", return_value="/fake"), patch.object(bootstrap, "tf"), patch.object(bootstrap, "outputs", side_effect=[values, {"deployed_image": image}]), patch.object(bootstrap, "verify_deployment"), patch.object(bootstrap.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="module.preset.aws_iam_openid_connect_provider.github[0]\n", stderr="")):
                bootstrap.bootstrap(operator, True)
                assert app_backend.read_text() == custom_backend
            with patch.object(deploy, "tf") as commands, patch.object(deploy, "outputs", return_value={"deployed_image": image}):
                deploy.plan(operator)
                assert any(f"-var=image_uri={image}" in call.args for call in commands.call_args_list)
                assert all("apply" not in call.args for call in commands.call_args_list)
            with patch.object(deploy, "tf"), patch.object(deploy, "outputs", return_value={"cluster_name": "demo", "service_name": "demo", "task_definition_arn": "task-arn", "url": "http://demo.invalid"}), patch.object(deploy, "run", side_effect=["task-arn", "old-image"]):
                try:
                    deploy.plan(operator, image=image, apply=True)
                    raise AssertionError("An ECS rollback was reported as success")
                except ValueError as error:
                    assert "requested image" in str(error)
            with patch.object(deploy, "outputs", return_value={"cluster_name": "demo", "service_name": "demo", "task_definition_arn": "task-arn"}), patch.object(deploy, "run", return_value="previous-task-arn"):
                try:
                    deploy.verify_deployment(operator, image)
                    raise AssertionError("A task configuration rollback was reported as success")
                except ValueError as error:
                    assert "requested task revision" in str(error)
            with patch.object(native, "tf"), patch.object(native.subprocess, "run", return_value=SimpleNamespace(returncode=2)):
                try:
                    native.foundation_plan(operator, require_unchanged=True)
                    raise AssertionError("CI would apply an unreviewed foundation change")
                except ValueError as error:
                    assert "operator review" in str(error)
            with patch.object(native, "run", return_value=json.dumps({"Account": "999999999999"})):
                try:
                    native.identity(operator)
                    raise AssertionError("A different AWS account was accepted")
                except ValueError as error:
                    assert "different account" in str(error)
            # Validate the consumer-owned root against this checkout before publication.
            for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
                path = consumer / "infra" / folder
                root = path / "main.tf"
                root.write_text(root.read_text().replace(f"git::https://github.com/{REPOSITORY}.git//infra/modules/{kind}?ref=infra-aws-container-v2.0.0", str(ROOT / "infra/modules" / kind)))
                run("terraform", f"-chdir={path}", "fmt")
            run(sys.executable, consumer / "infra/scripts/infra.py", "check")
            # Migration transfers ownership without changing Terraform, Docker or state.
            legacy = temporary / (profile + "-v1")
            shutil.copytree(ROOT / "infra/tests/fixtures/v1", legacy)
            shutil.copy2(consumer / ("package.json" if profile.startswith("typescript-") else "pyproject.toml"), legacy)
            shutil.copy2(docker, legacy / "Dockerfile")
            for folder in ["foundation", "app"]:
                shutil.copy2(consumer / "infra" / folder / "terraform.tfvars.json", legacy / "infra" / folder)
                (legacy / "infra" / folder / "backend.tf.json").write_text('{"project": "custom backend kept"}\n')
                (legacy / "infra" / folder / ".terraform.lock.hcl").write_text("# existing lock kept\n")
            (legacy / "infra/aws.json").write_text('{"account": "123456789012", "region": "ap-northeast-1", "role": "arn:aws:iam::123456789012:role/demo-deployment"}\n')
            native.write_json(legacy / "infra/.project-infra.json", {"release": "1.0.0", "profile": profile, "name": "demo", "region": "ap-northeast-1", "repository": "example/consumer", "branch": "main", "provider": "6.67.0", "files": {"Dockerfile": "already customized"}})
            workflow = legacy / ".github/workflows"
            workflow.mkdir(parents=True)
            for filename, template in [("deploy-infra.yml", "deploy.yml"), ("update-infra.yml", "update.yml")]:
                (workflow / filename).write_text((ROOT / "infra/python/project_presets_infra/recipe/legacy" / template).read_text().replace("__BRANCH__", '"main"'))
            # A custom workflow stops adoption before touching any file.
            original = (workflow / "deploy-infra.yml").read_text()
            (workflow / "deploy-infra.yml").write_text(original + "\n# consumer's extra job\n")
            before = snapshot(legacy)
            result = subprocess.run([*cli, "init", "--adopt", "--directory", str(legacy)], capture_output=True, text=True)
            assert result.returncode == 1 and "manual integration" in result.stderr and snapshot(legacy) == before
            (workflow / "deploy-infra.yml").write_text(original)
            before = snapshot(legacy)
            run(*cli, "init", "--adopt", "--directory", legacy)
            for filename, content in before.items():
                if filename in {"infra/.project-infra.json", ".github/workflows/deploy-infra.yml", ".github/workflows/update-infra.yml"}:
                    continue
                assert (legacy / filename).read_bytes() == content, filename
            assert not (legacy / "infra/.project-infra.json").exists()
            assert not (workflow / "update-infra.yml").exists()
            assert not (legacy / "infra/app/main.tf").exists()
            assert "infra-aws-container-v1.0.0" in (legacy / "infra/app/preset.tf.json").read_text()
            # Existing independent apps keep their Dockerfiles; no app marker is required.
            existing = temporary / (profile + "-existing")
            existing.mkdir()
            shutil.copy2(consumer / ("package.json" if profile.startswith("typescript-") else "pyproject.toml"), existing)
            (existing / "Dockerfile").write_text("custom Dockerfile\n")
            run(*cli, "init", "--directory", existing, "--profile", profile, "--name", "demo", "--repository", "example/consumer", "--module-version", "1.0.0")
            assert (existing / "Dockerfile").read_text() == "custom Dockerfile\n"
            assert "infra-aws-container-v1.0.0" in (existing / "infra/app/main.tf").read_text()
            if containers:
                entry = consumer / ("server.ts" if profile.startswith("typescript-") else "main.py")
                guard = "\nif (process.env.CUSTOM !== 'preserve') throw new Error('Missing configured environment');\n" if profile.startswith("typescript-") else "\nassert __import__('os').environ.get('CUSTOM') == 'preserve'\n"
                entry.write_text(entry.read_text() + guard)
                run(sys.executable, consumer / "infra/scripts/infra.py", "container-check")
            configured["secret_arns"] = {"TOKEN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:demo"}
            native.write_json(inputs, configured)
            with patch.object(deploy, "run") as commands:
                deploy.container_check(consumer)
                assert not any("aws" in call.args or "--detach" in call.args for call in commands.call_args_list)
        print("Infrastructure wheel, both project-owned roots, v1 migration, bootstrap recovery and deployment contracts passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--containers", action="store_true")
    check(parser.parse_args().containers)
