"""Prepare one consumer's pinned package, managed settings and native lockfile."""

import argparse
import json
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
        subprocess.run(command, cwd=target, check=True)

    profile = state["profile"]
    if profile in {"typescript-node", "typescript-hono", "typescript-next"}:
        filename = f"project-presets-demo-{selected}.tgz"
        source = str(artifacts / filename) if artifacts else f"{base}/{filename}"
        flags = ["--ignore-scripts", "--allow-git=root", "--allow-remote=root", "--no-audit", "--no-fund"]
        run("npm", "install", "--package-lock-only", "--save-dev", "--save-exact", source, *flags)
        run("npm", "ci", *flags)
        run("node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", profile, "--write", "--sync")
        run("node", "node_modules/project-presets-demo/scripts/apply-profile.mjs", profile, "--check")
        run("npm", "exec", "--", "eslint", ".")
        run("npm", "exec", "--", "tsc", "--noEmit")
        run("npm", "run", "build", "--if-present")
        run("npm", "run", "test", "--if-present")
    elif profile == "python-scripts":
        filename = f"project_presets_demo-{selected}-py3-none-any.whl"
        source = (artifacts / filename).as_uri() if artifacts else f"{base}/{filename}"
        run("uv", "add", "--dev", f"project-presets-demo @ {source}")
        run("uv", "run", "--locked", "project-presets-python", profile, "--write", "--sync")
        run("uv", "run", "--locked", "project-presets-python", profile, "--check")
        run("uv", "run", "--locked", "ruff", "check", ".")
    else:
        raise ValueError(f"Unsupported profile: {profile}")
    if json.loads((target / ".project-preset.json").read_text())["release"] != selected:
        raise ValueError("The artifact version differs from the selected release; do not merge")
    print(f"Updated {profile} from {state['release']} to {selected}; review and commit the diff")


if __name__ == "__main__":
    main()
