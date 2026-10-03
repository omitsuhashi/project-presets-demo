"""Prepare one consumer's pinned package, managed settings and native lockfile."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

REPOSITORY = "omitsuhashi/project-presets-demo"


def version(value):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Use a stable version such as 1.1.0")
    return tuple(map(int, value.split(".")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=".")
    parser.add_argument("--version", default="")
    parser.add_argument("--artifacts", type=Path, help="Local release artifacts for offline demos")
    args = parser.parse_args()
    target = Path(args.directory).resolve()
    state = json.loads((target / ".project-preset.json").read_text())
    current = version(state["release"])
    selected = args.version.removeprefix("v")
    if not selected:
        tags = subprocess.check_output([
            "gh", "api", f"repos/{REPOSITORY}/releases", "--paginate", "--jq",
            ".[] | select(.draft == false and .prerelease == false) | .tag_name",
        ], text=True).splitlines()
        compatible = [tag.removeprefix("v") for tag in tags if re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", tag)]
        compatible = [item for item in compatible if version(item)[0] == current[0] and version(item) >= current]
        if not compatible:
            raise ValueError("No compatible release found; major migrations require an explicit --version")
        selected = max(compatible, key=version)
    version(selected)
    base = f"https://github.com/{REPOSITORY}/releases/download/v{selected}"
    artifacts = args.artifacts.resolve() if args.artifacts else None

    def run(*command):
        subprocess.run(command, cwd=target, check=True, env={**os.environ, "CI": "true", "pnpm_config_ignore_scripts": "true"})

    profile = state["profile"]
    if profile in {"typescript-node", "typescript-hono", "typescript-next"}:
        if version(selected)[0] < 2:
            raise ValueError("Use the v1.5.0 updater for TypeScript 1.x; migrate with --version 2.0.0, or revert the migration PR")
        filename = f"project-presets-demo-{selected}.tgz"
        source = (artifacts / filename).as_uri() if artifacts else f"{base}/{filename}"
        run("npx", "--yes", "--ignore-scripts", "--allow-remote=root", "--package", source, "--", "project-presets", profile, "--setup", "--source", source)
        run("node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", profile, "--check")
        manager = subprocess.check_output([
            "node", "-p", "require('node:path').resolve(require('node:module').createRequire(require('node:fs').realpathSync('node_modules/project-presets-demo/scripts/apply-profile.mjs')).resolve('pnpm'), '../bin/pnpm.mjs')",
        ], cwd=target, text=True).strip()
        run("node", manager, "--ignore-workspace", "exec", "eslint", ".")
        run("node", manager, "--ignore-workspace", "exec", "tsc", "--noEmit")
        run("node", manager, "--ignore-workspace", "run", "--if-present", "build")
        run("node", manager, "--ignore-workspace", "run", "--if-present", "test")
    elif profile in {"python-scripts", "python-django", "python-fastapi"}:
        filename = f"project_presets_demo-{selected}-py3-none-any.whl"
        source = (artifacts / filename).as_uri() if artifacts else f"{base}/{filename}"
        run("uv", "add", "--dev", f"project-presets-demo @ {source}")
        run("uv", "run", "--locked", "project-presets-python", profile, "--write", "--sync")
        run("uv", "run", "--locked", "project-presets-python", profile, "--check")
        run("uv", "run", "--locked", "ruff", "check", ".")
        if profile == "python-django":
            run("uv", "run", "--locked", "python", "manage.py", "check")
            run("uv", "run", "--locked", "python", "manage.py", "test")
    else:
        raise ValueError(f"Unsupported profile: {profile}")
    if json.loads((target / ".project-preset.json").read_text())["release"] != selected:
        raise ValueError("The artifact version differs from the selected release; do not merge")
    print(f"Updated {profile} from {state['release']} to {selected}; review and commit the diff")


if __name__ == "__main__":
    main()
