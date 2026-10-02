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


manifest = json.loads((ROOT / "package.json").read_text())
python = tomllib.loads((ROOT / "pyproject.toml").read_text())
catalog = json.loads((ROOT / "profiles.json").read_text())
assert manifest["version"] == python["project"]["version"]
assert python["project"]["dependencies"] == ["ruff==" + catalog["python-scripts"]["devDependencies"]["ruff"]]

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
        catalog["python-scripts"]["devDependencies"]["ruff"] = ruff
        (provider / "profiles.json").write_text(json.dumps(catalog))
        text = (ROOT / "pyproject.toml").read_text().replace(python["project"]["version"], release).replace("ruff==0.16.10", f"ruff=={ruff}")
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
