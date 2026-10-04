"""Prepare one consumer's pinned package, managed settings and native lockfile."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from release_manifest import PROFILES, validate, version

REPOSITORY = "omitsuhashi/project-presets-demo"


def select(profile, current, requested="", artifacts=None):
    """Resolve a template version to its original, immutable artifact location."""
    if requested:
        version(requested)
    if requested == current:
        return {"version": current}
    candidates = []
    if artifacts:
        path = artifacts / "release-manifest.json"
        if path.exists():
            candidates.append(validate(json.loads(path.read_text()))["profiles"][profile])
        elif requested:
            filename = (f"project-presets-demo-{requested}.tgz" if profile.startswith("typescript-")
                        else f"project_presets_demo-{requested}-py3-none-any.whl")
            candidates.append({"version": requested, "tag": f"v{requested}", "asset": filename})
    else:
        pages = json.loads(subprocess.check_output([
            "gh", "api", f"repos/{REPOSITORY}/releases", "--paginate", "--slurp",
        ], text=True))
        releases = {item["tag_name"]: item for page in pages for item in page
                    if not item["draft"] and not item["prerelease"] and re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", item["tag_name"])}
        for tag, release in releases.items():
            names = {item["name"] for item in release["assets"]}
            if "release-manifest.json" in names:
                index = validate(json.loads(subprocess.check_output([
                    "gh", "release", "download", tag, "--repo", REPOSITORY,
                    "--pattern", "release-manifest.json", "--output", "-",
                ], text=True)))
                if index["tag"] != tag:
                    raise ValueError("Release index and GitHub tag differ")
                entry = index["profiles"][profile]
                origin = releases.get(entry["tag"])
                if origin and any(item["name"] == entry["asset"] for item in origin["assets"]):
                    candidates.append(entry)
            else:
                candidate = tag[1:]
                filename = (f"project-presets-demo-{candidate}.tgz" if profile.startswith("typescript-")
                            else f"project_presets_demo-{candidate}-py3-none-any.whl")
                if version(candidate) < (2, 2, 0) and filename in names:
                    candidates.append({"version": candidate, "tag": tag, "asset": filename})
    compatible = [entry for entry in candidates if (entry["version"] == requested if requested
                  else version(entry["version"])[0] == version(current)[0] and version(entry["version"]) > version(current))]
    if not compatible:
        if requested:
            raise ValueError(f"No published artifact for {profile} {requested}")
        return {"version": current}
    chosen = max(compatible, key=lambda entry: version(entry["version"]))
    if any((entry["tag"], entry["asset"]) != (chosen["tag"], chosen["asset"]) for entry in compatible if entry["version"] == chosen["version"]):
        raise ValueError("A template version must keep its original artifact URL")
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=".")
    parser.add_argument("--version", default="")
    parser.add_argument("--artifacts", type=Path, help="Local release artifacts for offline demos")
    args = parser.parse_args()
    target = Path(args.directory).resolve()
    state = json.loads((target / ".project-preset.json").read_text())
    version(state["release"])
    profile = state["profile"]
    if profile not in PROFILES:
        raise ValueError(f"Unsupported profile: {profile}")
    artifacts = args.artifacts.resolve() if args.artifacts else None
    entry = select(profile, state["release"], args.version.removeprefix("v"), artifacts)
    selected = entry["version"]
    if selected == state["release"]:
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                output.write("changed=false\n")
        print(f"{profile} is already at {selected}; no update needed")
        return
    tag = entry["tag"]
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}"
    filename = entry["asset"]
    source = (artifacts / filename).as_uri() if artifacts else f"{base}/{filename}"

    def run(*command):
        subprocess.run(command, cwd=target, check=True, env={**os.environ, "CI": "true", "pnpm_config_ignore_scripts": "true"})

    if profile in {"typescript-node", "typescript-hono", "typescript-next"}:
        if version(selected)[0] < 2:
            raise ValueError("Use the v1.5.0 updater for TypeScript 1.x; migrate with --version 2.0.0, or revert the migration PR")
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
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("changed=true\n")
    print(f"Updated {profile} from {state['release']} to {selected}; review and commit the diff")


if __name__ == "__main__":
    main()
