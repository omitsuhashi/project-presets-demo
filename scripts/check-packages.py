"""Exercise release artifacts, both native locks, local overrides and rollback."""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import ExitStack
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def run(cwd, *command, expected=0):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == expected, f"{' '.join(map(str, command))}\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


def git(cwd, *command):
    return run(cwd, "git", *command)


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
assert python["project"]["dependencies"] == ["ruff==" + catalog["python-scripts"]["devDependencies"]["ruff"]]
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
    for release, ruff, node_types in [("1.0.0", "0.16.9", "24.19.0"), ("2.0.0", "0.16.10", "24.19.1")]:
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
        run(provider, "npm", "pack", "--ignore-scripts", "--pack-destination", str(artifacts))
        run(provider, "uv", "build", "--out-dir", str(artifacts))

    ts, py = temp / "typescript", temp / "python"
    init(ts)
    init(py)
    (ts / "package.json").write_text('{"name":"consumer","private":true,"type":"module","scripts":{"custom":"keep"}}\n')
    flags = ["--ignore-scripts", "--no-audit", "--no-fund"]
    run(ts, "npm", "install", "--save-dev", "--save-exact", "--allow-remote=root", remote + "/project-presets-demo-1.0.0.tgz", *flags)
    cli = ["node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", "typescript-node"]
    run(ts, *cli, "--write", "--sync")
    run(ts, *cli, "--check")
    (ts / "main.ts").write_text("export const message = 'consumer';\nconsole.log(message);\n")
    with (ts / "eslint.config.mjs").open("a") as file:
        file.write("\n// Consumer owns this comment.\n")
    ts_source = (ts / "main.ts").read_bytes()
    ts_config = (ts / "eslint.config.mjs").read_bytes()
    commit(ts, "Adopt old npm package")
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
    run(py, "uv", "add", "--dev", "project-presets-demo @ " + (artifacts / "project_presets_demo-1.0.0-py3-none-any.whl").as_uri())
    pycli = ["uv", "run", "--locked", "project-presets-python", "python-scripts"]
    before = (py / "pyproject.toml").read_bytes()
    run(py, *pycli, "--adopt")
    assert (py / "pyproject.toml").read_bytes() == before
    assert not (py / ".project-preset.json").exists()
    run(py, *pycli, "--write", expected=1)
    run(py, *pycli, "--adopt", "--write", "--sync")
    run(py, *pycli, "--check")
    py_config = tomllib.loads((py / "pyproject.toml").read_text())["tool"]["ruff"]
    py_source = (py / "main.py").read_bytes()
    commit(py, "Adopt old Python wheel")
    managed = py / ".project-presets/ruff/scripts.toml"
    original = managed.read_bytes()
    managed.write_bytes(original + b"\n# Local edit\n")
    run(py, *pycli, "--write", expected=1)
    managed.write_bytes(original)
    run(py, "uv", "add", "--dev", "project-presets-demo @ " + (artifacts / "project_presets_demo-2.0.0-py3-none-any.whl").as_uri())
    run(py, *pycli, "--check", expected=1)
    for consumer in [ts, py]:
        updater = [sys.executable, str(ROOT / "scripts/update-consumer.py"), "--artifacts", str(artifacts)]
        run(consumer, *updater, "--version", "bad-version", expected=1)
        run(consumer, *updater, "--version", "2.0.0")
        assert json.loads((consumer / ".project-preset.json").read_text())["release"] == "2.0.0"
        revision = commit(consumer, "Update packages and locks")
        if consumer == ts:
            assert json.loads((ts / "package-lock.json").read_text())["packages"]["node_modules/@types/node"]["version"] == "24.19.1"
            assert (ts / "eslint.config.mjs").read_bytes() == ts_config
            assert (ts / "main.ts").read_bytes() == ts_source
            assert json.loads((ts / "package.json").read_text())["scripts"]["custom"] == "keep"
        else:
            assert run(py, "uv", "run", "--locked", "ruff", "--version") == "ruff 0.16.10"
            assert tomllib.loads((py / "pyproject.toml").read_text())["tool"]["ruff"] == py_config
            assert (py / "main.py").read_bytes() == py_source
            assert 'extend-select = ["C4"]' in (py / ".project-presets/ruff/base.toml").read_text()
        git(consumer, "revert", "--no-edit", revision)
        if consumer == ts:
            run(ts, "npm", "ci", "--allow-remote=root", *flags)
            run(ts, *cli, "--check")
            assert json.loads((ts / "package-lock.json").read_text())["packages"]["node_modules/@types/node"]["version"] == "24.19.0"
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
        run(consumer, "uv", "add", "--dev", "project-presets-demo @ " + (artifacts / "project_presets_demo-1.0.0-py3-none-any.whl").as_uri())
        profile = f"python-{kind}"
        cli = [str(consumer / ".venv/bin/project-presets-python"), profile]
        before = (consumer / "pyproject.toml").read_bytes()
        run(consumer, *cli)
        assert (consumer / "pyproject.toml").read_bytes() == before
        assert not (consumer / ".project-preset.json").exists()
        run(consumer, *cli, "--write", "--sync")
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
