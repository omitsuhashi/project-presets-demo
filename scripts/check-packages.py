"""Exercise release artifacts, both native locks, local overrides and rollback."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
from contextlib import ExitStack
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def run(cwd, *command, expected=0):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env={**os.environ, "CI": "true"})
    assert result.returncode == expected, f"{' '.join(map(str, command))}\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


def git(cwd, *command):
    return run(cwd, "git", *command)


def pnpm(cwd, *command):
    return run(cwd, "node", str(ROOT / "node_modules/pnpm/bin/pnpm.mjs"), "--ignore-workspace", *command)


def init(path):
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Package Check")
    git(path, "config", "user.email", "check@example.invalid")
    (path / ".gitignore").write_text("node_modules/\n.venv/\n.ruff_cache/\n__pycache__/\n")


def commit(path, message):
    git(path, "add", ".")
    git(path, "commit", "-m", message)
    return git(path, "rev-parse", "HEAD")


def framework_check(consumer, kind, cli):
    run(consumer, "uv", "sync", "--locked", "--no-dev")
    runtime = str(consumer / ".venv/bin/python")
    run(consumer, runtime, "-c", 'import importlib.metadata as m; assert "ruff" not in m.packages_distributions(); assert "project_presets_demo" not in m.packages_distributions()')
    if kind == "django":
        run(consumer, runtime, "manage.py", "check")
        run(consumer, runtime, "manage.py", "test")
    else:
        run(consumer, runtime, "-m", "unittest", "discover")
    run(consumer, "uv", "sync", "--locked")
    run(consumer, *cli, "--check")
    run(consumer, "uv", "run", "--locked", "ruff", "check", ".")


manifest = json.loads((ROOT / "package.json").read_text())
python = tomllib.loads((ROOT / "pyproject.toml").read_text())
catalog = json.loads((ROOT / "profiles.json").read_text())
assert manifest["version"] == python["project"]["version"]
assert manifest["packageManager"] == "pnpm@" + manifest["dependencies"]["pnpm"]
assert python["project"]["dependencies"] == ["ruff==" + catalog["python-scripts"]["devDependencies"]["ruff"]]
current_ruff = catalog["python-scripts"]["devDependencies"]["ruff"]
current_node_types = catalog["typescript-node"]["devDependencies"]["@types/node"]
assert (ROOT / "profiles/python-scripts/requirements-dev.txt").read_text().strip() == f"ruff=={current_ruff}"
for name, requirements in python["project"]["optional-dependencies"].items():
    profile = catalog[f"python-{name}"]
    assert requirements == [f"{package}=={version}" for package, version in profile["dependencies"].items()]
    assert profile["devDependencies"] == catalog["python-scripts"]["devDependencies"]
    assert (ROOT / profile["ruff"]).exists()
old_frameworks = {"django": "6.1", "fastapi": "0.142.1", "uvicorn": "0.53.0"}

with tempfile.TemporaryDirectory(prefix="project-presets-packages-") as directory, ExitStack() as cleanup:
    temp = Path(directory)
    provider = temp / "provider"
    provider.mkdir()
    artifacts = temp / "artifacts"
    artifacts.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(artifacts)))
    cleanup.callback(server.server_close)
    cleanup.callback(server.shutdown)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    remote = f"http://127.0.0.1:{server.server_port}"
    for name in ["package.json", "pyproject.toml", "README.md", "LICENSE", "profiles.json", "profiles", "typescript", "python", "scripts"]:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, provider / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, provider / name)
    for release, ruff, node_types in [("1.0.0", "0.16.9", "24.19.0"), ("2.0.0", current_ruff, current_node_types)]:
        manifest["version"] = release
        (provider / "package.json").write_text(json.dumps(manifest))
        catalog["typescript-node"]["devDependencies"]["@types/node"] = node_types
        for profile in catalog.values():
            if profile["language"] == "python":
                profile["devDependencies"]["ruff"] = ruff
        text = (ROOT / "pyproject.toml").read_text().replace(python["project"]["version"], release).replace(python["project"]["dependencies"][0], f"ruff=={ruff}")
        for kind, dependencies in python["project"]["optional-dependencies"].items():
            for dependency in dependencies:
                name, pin = dependency.split("==")
                selected = old_frameworks[name] if release == "1.0.0" else pin
                text = text.replace(dependency, f"{name}=={selected}")
                catalog[f"python-{kind}"]["dependencies"][name] = selected
        (provider / "profiles.json").write_text(json.dumps(catalog))
        (provider / "pyproject.toml").write_text(text)
        if release == "2.0.0":
            with (provider / "python/project_presets_demo/config/base.toml").open("a") as file:
                file.write('\nextend-select = ["C4"]\n')
        pnpm(provider, "pack", "--config.ignore-scripts=true", "--pack-destination", str(artifacts))
        run(provider, "uv", "build", "--out-dir", str(artifacts))

    # Real npx / uvx entry points must bootstrap projects without manifests.
    for profile, settings in catalog.items():
        consumer = temp / "empty projects" / f"日本語 {profile}"
        npm_source = remote + "/project-presets-demo-2.0.0.tgz"
        wheel_source = (artifacts / "project_presets_demo-2.0.0-py3-none-any.whl").as_uri()
        typescript = settings["language"] == "typescript"
        source = npm_source if typescript else wheel_source
        entry = (["npx", "--yes", "--allow-remote=root", "--ignore-scripts", source, profile]
                 if typescript else ["uvx", "--python", "3.12", "--from", source, "project-presets-python", profile])
        if profile in {"typescript-node", "python-django"}:
            consumer.mkdir(parents=True)
        existed = consumer.exists()
        preview = json.loads(run(temp, *entry, str(consumer), "--source", source))
        assert preview["profile"] == profile
        assert ("package.json" if typescript else "pyproject.toml") in preview["create"]
        assert ".github/workflows/update-presets.yml" in preview["create"]
        assert consumer.exists() == existed
        assert not consumer.exists() or not list(consumer.iterdir()), "Preview must not create project files"
        run(temp, *entry, str(consumer), "--check", "--source", source, expected=1)
        assert consumer.exists() == existed
        assert not consumer.exists() or not list(consumer.iterdir())
        run(temp, *entry, str(consumer), "--setup", "--source", source)
        workflow = consumer / ".github/workflows/update-presets.yml"
        automation = workflow.read_bytes()
        assert b"update-consumer.yml@v2.0.0" in automation
        assert b"cron: '15 2 * * 1'" in automation and b"workflow_dispatch:" in automation
        assert b"contents: write" in automation and b"pull-requests: write" in automation
        run(temp, *entry, str(consumer), "--check", "--source", source)
        name = "package.json" if typescript else "pyproject.toml"
        text = (consumer / name).read_bytes()
        created = json.loads(text) if typescript else tomllib.loads(text.decode())["project"]
        assert created["name"] == profile
        assert created["version"] == "0.0.0"
        if typescript:
            assert created["dependencies"] == settings.get("dependencies", {})
            assert created["private"] and created["type"] == "module"
            assert created["packageManager"] == manifest["packageManager"]
            assert (consumer / "pnpm-lock.yaml").exists() and not (consumer / "package-lock.json").exists()
        else:
            assert created["requires-python"] == ">=3.12,<3.13"
        run(temp, *entry, str(consumer), "--setup", "--source", source)
        assert (consumer / name).read_bytes() == text, "Repeat setup must preserve the manifest"
        assert workflow.read_bytes() == automation, "Repeat setup must preserve the update workflow"
        workflow.unlink()
        run(temp, *entry, str(consumer), "--check", "--source", source, expected=1)
        run(temp, *entry, str(consumer), "--setup", "--source", source)
        assert workflow.read_bytes() == automation, "Setup restores a missing update workflow"
        (consumer / name).unlink()
        run(temp, *entry, str(consumer), "--setup", "--source", source, expected=1)
        assert not (consumer / name).exists(), "A deleted adopted manifest needs recovery, not reinitialization"
        print(f"PASS: {profile} bootstraps its manifest, dependencies and update workflow; preview is read-only and setup restores the workflow")

    legacy = temp / "npm-migration"
    init(legacy)
    (legacy / "package.json").write_text(json.dumps({
        "name": "legacy-consumer", "private": True, "type": "module", "packageManager": "npm@12.1.0",
        "dependencies": {"ms": "2.1.2"}, "scripts": {"test": "node main.ts"},
    }))
    (legacy / "main.ts").write_text("export const message = 'preserved';\n")
    old_source = "https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.5.0/project-presets-demo-1.5.0.tgz"
    run(legacy, "npx", "--yes", "--allow-remote=root", "--ignore-scripts", old_source, "typescript-node", "--setup")
    old_lock = (legacy / "package-lock.json").read_bytes()
    with (legacy / "eslint.config.mjs").open("a") as file:
        file.write("\n// Application-owned setting.\n")
    config = (legacy / "eslint.config.mjs").read_bytes()
    commit(legacy, "Adopt published npm preset")
    new_entry = ["npx", "--yes", "--allow-remote=root", "--ignore-scripts", remote + "/project-presets-demo-2.0.0.tgz", "typescript-node"]
    run(legacy, *new_entry, "--setup", "--source", remote + "/project-presets-demo-1.0.0.tgz", expected=1)
    assert (legacy / "package-lock.json").read_bytes() == old_lock, "Failed migration must keep the original npm lock"
    git(legacy, "restore", ".")
    (legacy / "pnpm-lock.yaml").unlink()
    updater = [sys.executable, str(ROOT / "scripts/update-consumer.py"), "--artifacts", str(artifacts)]
    run(legacy, *updater, "--version", "1.5.0", expected=1)
    run(legacy, *updater, "--version", "2.0.0")
    migrated = json.loads((legacy / "package.json").read_text())
    assert migrated["packageManager"] == manifest["packageManager"]
    assert migrated["dependencies"]["ms"] == "2.1.2"
    assert migrated["scripts"]["test"] == "node main.ts"
    assert (legacy / "node_modules/ms/package.json").exists()
    assert (legacy / "eslint.config.mjs").read_bytes() == config
    assert (legacy / "pnpm-lock.yaml").exists() and not (legacy / "package-lock.json").exists()
    workflow = (ROOT / ".github/workflows/update-consumer.yml").read_text()
    staging = workflow[workflow.index("          for path in "):workflow.index("          if git diff --cached")]
    run(legacy, "bash", "-e", "-c", "PRESET_DIRECTORY=.\n" + textwrap.dedent(staging))
    assert "D\tpackage-lock.json" in git(legacy, "diff", "--cached", "--name-status")
    assert "A\tpnpm-lock.yaml" in git(legacy, "diff", "--cached", "--name-status")
    migration = commit(legacy, "Migrate npm lock to pnpm")
    git(legacy, "revert", "--no-edit", migration)
    run(legacy, "npm", "ci", "--allow-remote=root", "--ignore-scripts")
    run(legacy, "node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", "typescript-node", "--check")
    assert (legacy / "package-lock.json").read_bytes() == old_lock
    assert not (legacy / "pnpm-lock.yaml").exists()
    assert git(legacy, "status", "--porcelain") == ""
    print("PASS: published npm 1.5.0 migrates to pnpm, preserves app dependencies/settings, retains npm lock on failure and reverts")

    ts, py = temp / "typescript", temp / "python"
    init(ts)
    init(py)
    (ts / "package.json").write_text('{"name":"consumer","private":true,"type":"module","scripts":{"custom":"keep"}}\n')
    npm_source = remote + "/project-presets-demo-1.0.0.tgz"
    one_shot = ["npx", "--yes", "--allow-remote=root", "--ignore-scripts", npm_source, "typescript-node"]
    cli = ["node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", "typescript-node"]
    before = (ts / "package.json").read_bytes()
    run(ts, *one_shot, "--setup", "--check", expected=1)
    run(ts, *one_shot, "--setup", "--source", "", expected=1)
    preview = json.loads(run(ts, *one_shot))
    assert preview["source"] == "https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.0.0/project-presets-demo-1.0.0.tgz"
    run(ts, *one_shot, "--source", npm_source)
    assert (ts / "package.json").read_bytes() == before
    assert not (ts / "node_modules").exists()
    assert not (ts / ".project-preset.json").exists()
    run(ts, *one_shot, "--setup", "--source", npm_source)
    run(ts, *cli, "--check")
    ready = {name: (ts / name).read_bytes() for name in ["package.json", "pnpm-lock.yaml", ".project-preset.json", "eslint.config.mjs", "tsconfig.json"]}
    run(ts, *cli, "--setup")
    assert all((ts / name).read_bytes() == content for name, content in ready.items())
    pnpm(ts, "exec", "eslint", "--version")
    pnpm(ts, "exec", "tsc", "--version")
    ts_workflow = ts / ".github/workflows/update-presets.yml"
    ts_workflow.write_text(ts_workflow.read_text().replace("15 2 * * 1", "45 2 * * 1") + "\n# Consumer-owned schedule.\n")
    ts_automation = ts_workflow.read_bytes()
    (ts / "main.ts").write_text("export const message = 'consumer';\nconsole.log(message);\n")
    with (ts / "eslint.config.mjs").open("a") as file:
        file.write("\n// Consumer owns this comment.\n")
    ts_source = (ts / "main.ts").read_bytes()
    ts_config = (ts / "eslint.config.mjs").read_bytes()
    commit(ts, "Adopt old pnpm package")
    (ts / "eslint.config.mjs").unlink()
    run(ts, *cli, "--write", expected=1)
    (ts / "eslint.config.mjs").write_bytes(ts_config)

    (py / "pyproject.toml").write_text('''[project]
name = "consumer"
version = "0.0.0"
requires-python = ">=3.12,<3.13"

[tool.ruff]
extend = ".project-presets/ruff/scripts.toml"
target-version = "py312"
line-length = 100

[tool.ruff.lint]
ignore = ["F401"]
''')
    (py / "main.py").write_text('import math\n\nprint("consumer")\n')
    wheel = (artifacts / "project_presets_demo-1.0.0-py3-none-any.whl").as_uri()
    py_one_shot = ["uvx", "--python", "3.12", "--from", wheel, "project-presets-python", "python-scripts"]
    pycli = ["uv", "run", "--locked", "project-presets-python", "python-scripts"]
    before = (py / "pyproject.toml").read_bytes()
    preview = json.loads(run(py, *py_one_shot, "--adopt"))
    assert preview["source"] == "https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.0.0/project_presets_demo-1.0.0-py3-none-any.whl"
    assert (py / "pyproject.toml").read_bytes() == before
    assert not (py / ".project-preset.json").exists()
    assert not (py / ".venv").exists()
    run(py, *py_one_shot, "--write", expected=1)
    run(py, *py_one_shot, "--setup", "--check", expected=2)
    run(py, *py_one_shot, "--adopt", "--setup", "--source", "", expected=1)
    run(py, *py_one_shot, "--adopt", "--setup", "--source", wheel)
    run(py, *py_one_shot, "--check")
    run(py, *pycli, "--check")
    ready = {name: (py / name).read_bytes() for name in ["pyproject.toml", "uv.lock", ".project-preset.json"]}
    run(py, *pycli, "--setup")
    assert all((py / name).read_bytes() == content for name, content in ready.items())
    py_config = tomllib.loads((py / "pyproject.toml").read_text())["tool"]["ruff"]
    py_workflow = py / ".github/workflows/update-presets.yml"
    py_workflow.write_text(py_workflow.read_text().replace("15 2 * * 1", "45 2 * * 1") + "\n# Consumer-owned schedule.\n")
    py_automation = py_workflow.read_bytes()
    py_source = (py / "main.py").read_bytes()
    commit(py, "Adopt old Python wheel")
    managed = py / ".project-presets/ruff/scripts.toml"
    original = managed.read_bytes()
    managed.write_bytes(original + b"\n# Local edit\n")
    run(py, *pycli, "--write", expected=1)
    managed.write_bytes(original)
    for consumer in [ts, py]:
        if consumer == ts:
            source = remote + "/project-presets-demo-2.0.0.tgz"
            update_cli = ["npx", "--yes", "--allow-remote=root", "--ignore-scripts", source, "typescript-node"]
        else:
            source = (artifacts / "project_presets_demo-2.0.0-py3-none-any.whl").as_uri()
            update_cli = ["uvx", "--python", "3.12", "--from", source, "project-presets-python", "python-scripts"]
        run(consumer, *update_cli, "--check", expected=1)
        run(consumer, *update_cli, "--setup", "--source", source)
        run(consumer, *update_cli, "--check")
        updater = [sys.executable, str(ROOT / "scripts/update-consumer.py"), "--artifacts", str(artifacts)]
        run(consumer, *updater, "--version", "bad-version", expected=1)
        run(consumer, *updater, "--version", "2.0.0")
        assert json.loads((consumer / ".project-preset.json").read_text())["release"] == "2.0.0"
        revision = commit(consumer, "Update packages and locks")
        if consumer == ts:
            assert json.loads((ts / "node_modules/@types/node/package.json").read_text())["version"] == current_node_types
            assert (ts / "eslint.config.mjs").read_bytes() == ts_config
            assert (ts / "main.ts").read_bytes() == ts_source
            assert ts_workflow.read_bytes() == ts_automation
            assert json.loads((ts / "package.json").read_text())["scripts"]["custom"] == "keep"
        else:
            assert run(py, "uv", "run", "--locked", "ruff", "--version") == f"ruff {current_ruff}"
            assert tomllib.loads((py / "pyproject.toml").read_text())["tool"]["ruff"] == py_config
            assert (py / "main.py").read_bytes() == py_source
            assert py_workflow.read_bytes() == py_automation
            assert 'extend-select = ["C4"]' in (py / ".project-presets/ruff/base.toml").read_text()
        git(consumer, "revert", "--no-edit", revision)
        if consumer == ts:
            pnpm(ts, "install", "--frozen-lockfile", "--ignore-scripts")
            run(ts, *cli, "--check")
            assert json.loads((ts / "node_modules/@types/node/package.json").read_text())["version"] == "24.19.0"
        else:
            run(py, "uv", "sync", "--locked")
            run(py, *pycli, "--check")
            assert run(py, "uv", "run", "--locked", "ruff", "--version") == "ruff 0.16.9"
        assert git(consumer, "status", "--porcelain") == ""
        print(f"PASS: {consumer.name} package update, native lock, overrides, drift rejection and revert")

    for kind in ["django", "fastapi"]:
        consumer = temp / kind
        init(consumer)
        shutil.copytree(ROOT / "examples" / kind, consumer, dirs_exist_ok=True)
        (consumer / "pyproject.toml").write_text('''[project]
name = "framework-consumer"
version = "0.0.0"
requires-python = ">=3.12,<3.13"

[tool.consumer]
keep = "application-owned"
''')
        profile = f"python-{kind}"
        one_shot = ["uvx", "--python", "3.12", "--from", wheel, "project-presets-python", profile]
        cli = [str(consumer / ".venv/bin/project-presets-python"), profile]
        before = (consumer / "pyproject.toml").read_bytes()
        run(consumer, *one_shot)
        assert (consumer / "pyproject.toml").read_bytes() == before
        assert not (consumer / ".project-preset.json").exists()
        assert not (consumer / ".venv").exists()
        run(consumer, *one_shot, "--setup", "--source", wheel)
        run(consumer, *one_shot, "--check")
        run(consumer, *cli, "--check")
        with (consumer / "pyproject.toml").open("a") as file:
            file.write('\n[tool.ruff.lint]\nignore = ["F401"]\n')
        original = (consumer / "pyproject.toml").read_bytes()
        state = json.loads((consumer / ".project-preset.json").read_text())
        assert state["dependencies"] == {name: old_frameworks[name] for name in catalog[profile]["dependencies"]}
        name = next(iter(state["dependencies"]))
        (consumer / "pyproject.toml").write_text(original.decode().replace(f"{name}=={old_frameworks[name]}", f"{name}>=0"))
        run(consumer, *cli, "--write", expected=1)
        assert f"{name}>=0" in (consumer / "pyproject.toml").read_text()
        removed = original.decode().replace(f'"{name}=={old_frameworks[name]}",', '').replace(f'"{name}=={old_frameworks[name]}"', '')
        assert f"{name}=={old_frameworks[name]}" not in tomllib.loads(removed)["project"]["dependencies"]
        (consumer / "pyproject.toml").write_text(removed)
        run(consumer, *cli, "--write", expected=1)
        (consumer / "pyproject.toml").write_bytes(original)
        other = "python-fastapi" if kind == "django" else "python-django"
        run(consumer, cli[0], other, "--write", expected=1)
        assert (consumer / "pyproject.toml").read_bytes() == original
        bad = 'from django.db import models\n\nclass Bad(models.Model):\n    title = models.CharField(null=True, max_length=30)\n' if kind == "django" else 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/items/{item_id}")\ndef items():\n    return {}\n'
        (consumer / "bad.py").write_text(bad + '\nprint("service")\n')
        errors = json.loads(run(consumer, "uv", "run", "--locked", "ruff", "check", "bad.py", "--output-format", "json", expected=1))
        assert {"DJ001" if kind == "django" else "FAST003", "T201"} <= {item["code"] for item in errors}
        (consumer / "bad.py").unlink()
        sources = {path.relative_to(consumer): path.read_bytes() for path in consumer.rglob("*.py") if ".venv" not in path.parts}
        tools = tomllib.loads((consumer / "pyproject.toml").read_text())["tool"]
        settings = {name: tools[name] for name in ["consumer", "ruff"]}

        framework_check(consumer, kind, cli)
        commit(consumer, "Adopt framework wheel")
        updater = [sys.executable, str(ROOT / "scripts/update-consumer.py"), "--artifacts", str(artifacts), "--version", "2.0.0"]
        run(consumer, *updater)
        updated = json.loads((consumer / ".project-preset.json").read_text())
        assert updated["dependencies"] == catalog[profile]["dependencies"]
        assert updated["release"] == "2.0.0"
        tools = tomllib.loads((consumer / "pyproject.toml").read_text())["tool"]
        assert {name: tools[name] for name in settings} == settings
        assert all((consumer / name).read_bytes() == content for name, content in sources.items())
        assert 'extend-select = ["C4"]' in (consumer / ".project-presets/ruff/base.toml").read_text()
        framework_check(consumer, kind, cli)
        revision = commit(consumer, "Update framework and native lock")
        git(consumer, "revert", "--no-edit", revision)
        framework_check(consumer, kind, cli)
        assert json.loads((consumer / ".project-preset.json").read_text()) == state
        assert git(consumer, "status", "--porcelain") == ""
        print(f"PASS: {profile} rules, runtime without dev tools, framework update, overrides, drift rejection and revert")
