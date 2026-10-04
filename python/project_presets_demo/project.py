"""Read, apply and verify plans using the native uv manifest and lock operations."""

import hashlib
import importlib.metadata as metadata
import json
import subprocess
from pathlib import Path

import tomllib

from .plan import plan_update, requirement_name


def read_preset():
    root = Path(__file__).parent
    publication = root / "release.json"
    return {"version": metadata.version("project-presets-demo"),
            "requirements": metadata.requires("project-presets-demo"),
            "publication": json.loads(publication.read_text()) if publication.exists() else None,
            "configs": {source.name: source.read_bytes() for source in sorted((root / "config").glob("*.toml"))},
            "workflow": (root / "update-presets.yml").read_text()}


def read_project(target, preset):
    manifest = target / "pyproject.toml"
    marker = target / ".project-preset.json"
    names = [f".project-presets/ruff/{name}" for name in preset["configs"]] + [".github/workflows/update-presets.yml"]
    return {"name": target.name, "manifest_text": manifest.read_text() if manifest.exists() else None,
            "previous": json.loads(marker.read_text()) if marker.exists() else None,
            "legacy_submodule": (target / ".project-presets/.git").exists(),
            "files": {name: (target / name).read_bytes() for name in names if (target / name).exists()}}


def check_environment(target, versions):
    installed = json.loads(subprocess.check_output([
        "uv", "run", "--no-sync", "python", "-c",
        "import importlib.metadata as m,json,sys; print(json.dumps({name:m.version(name) for name in sys.argv[1:]}))",
        *versions,
    ], cwd=target, text=True))
    if installed != versions:
        raise ValueError("Sync the executing preset release and its dependencies in the project environment")


def verify_project(target, project, plan):
    if ".github/workflows/update-presets.yml" not in project["files"]:
        raise ValueError("Run --setup to add the automatic update workflow")
    manifest = tomllib.loads(project["manifest_text"])
    dev = manifest.get("dependency-groups", {}).get("dev", [])
    has_preset = any(isinstance(item, str) and requirement_name(item) == "project-presets-demo" for item in dev)
    if project["previous"] != plan.state or plan.manifest_suffix or not has_preset:
        raise ValueError("Apply the installed preset before merging")
    for name, digest in plan.state["files"].items():
        if hashlib.sha256(project["files"][name]).hexdigest() != digest:
            raise ValueError(f"Apply the installed preset for {name}")
    locked = tomllib.loads((target / "uv.lock").read_text())["package"]
    versions = {item["name"]: item["version"] for item in locked}
    if versions.get("project-presets-demo") != plan.state["release"] or versions.get("ruff") != plan.state["devDependencies"]["ruff"]:
        raise ValueError("Sync the preset and Ruff with the uv lock before merging")
    for name, version in plan.state.get("dependencies", {}).items():
        if f"{name}=={version}" not in [item.lower().strip() for item in manifest["project"].get("dependencies", [])] or versions.get(name) != version:
            raise ValueError(f"Sync the runtime dependency {name} with the uv lock before merging")
    subprocess.run(["uv", "lock", "--check"], cwd=target, check=True)
    check_environment(target, plan.versions)


def apply_plan(target, plan, sync=False):
    manifest_path = target / "pyproject.toml"
    if plan.initialize:
        target.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("x") as file:
            file.write(plan.manifest_text)
    for command in plan.commands:
        subprocess.run(command, cwd=target, check=True)
    text = manifest_path.read_text() + plan.manifest_suffix
    writes = {**plan.writes, "pyproject.toml": text.encode(),
              ".project-preset.json": (json.dumps(plan.state, indent=2) + "\n").encode()}
    # Stage before replacement; on filesystem failure keep files for recovery.
    staged = []
    for name, content in writes.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".preset-new")
        with temporary.open("xb") as file:
            file.write(content)
        staged.append((temporary, destination))
    for temporary, destination in staged:
        temporary.replace(destination)
    if sync:
        subprocess.run(["uv", "sync", "--locked"], cwd=target, check=True)
        check_environment(target, plan.versions)
    print("Automatic update PRs: commit .github/workflows/update-presets.yml with the preset files and push to the GitHub default branch. Enable Actions > General > Allow GitHub Actions to create and approve pull requests. Existing workflows are preserved; review their schedule and tests.")


def apply(args):
    if args.sync and not args.write:
        raise ValueError("--sync requires --write or --setup")
    target = Path(args.directory).resolve()
    preset = read_preset()
    project = read_project(target, preset)
    plan = plan_update(project, preset, profile=args.profile, adopt=args.adopt, source=args.source, check=args.check)
    print(json.dumps(plan.summary, indent=2))
    if args.check:
        verify_project(target, project, plan)
    if args.write:
        apply_plan(target, plan, args.sync)
