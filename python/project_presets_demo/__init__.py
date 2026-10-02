"""Apply the installed Python preset without replacing project-owned settings."""

import argparse
import hashlib
import importlib.metadata as metadata
import json
import subprocess
from pathlib import Path

import tomllib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=["python-scripts"])
    parser.add_argument("directory", nargs="?", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--adopt", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    try:
        apply(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


def apply(args):
    if args.sync and not args.write:
        raise ValueError("--sync requires --write")
    target = Path(args.directory).resolve()
    manifest_path = target / "pyproject.toml"
    text = manifest_path.read_text()
    manifest = tomllib.loads(text)
    release = metadata.version("project-presets-demo")
    ruff = next(item.removeprefix("ruff==") for item in metadata.requires("project-presets-demo") if item.startswith("ruff=="))
    marker = target / ".project-preset.json"
    previous = json.loads(marker.read_text()) if marker.exists() else None
    if previous and previous["profile"] != args.profile:
        raise ValueError("Changing profiles requires an application migration")
    if (target / ".project-presets/.git").exists():
        raise ValueError("Remove the old preset submodule in a reviewed migration before adopting the wheel")
    config = manifest.get("tool", {}).get("ruff")
    if previous and config is None:
        raise ValueError("Ruff configuration was deleted locally; restore before updating")
    extend = ".project-presets/ruff/scripts.toml"
    if config is not None:
        if config.get("extend") != extend or (not previous and not args.adopt):
            raise ValueError(f"Integrate [tool.ruff] extend = {extend!r}, then use --adopt to preserve existing settings")
    else:
        text += f'\n[tool.ruff]\nextend = "{extend}"\ntarget-version = "py312"\n'
    writes = {}
    hashes = {}
    for source in sorted((Path(__file__).parent / "config").glob("*.toml")):
        name = f".project-presets/ruff/{source.name}"
        content = source.read_bytes()
        hashes[name] = hashlib.sha256(content).hexdigest()
        destination = target / name
        if destination.exists():
            current = hashlib.sha256(destination.read_bytes()).hexdigest()
            if current != hashes[name] and current != (previous or {}).get("files", {}).get(name):
                raise ValueError(f"{name} was changed locally; resolve before updating")
        elif name in (previous or {}).get("files", {}):
            raise ValueError(f"{name} was deleted locally; restore before updating")
        writes[destination] = content
    if previous and set(previous["files"]) - set(hashes):
        raise ValueError("Removing managed configuration requires a migration")
    state = {"profile": args.profile, "release": release, "files": hashes, "devDependencies": {"ruff": ruff}}
    print(json.dumps({"profile": args.profile, "release": release, "ruff": ruff, "files": list(hashes)}, indent=2))
    if args.check:
        if previous != state or config is None:
            raise ValueError("Apply the installed preset before merging")
        for name, digest in hashes.items():
            if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Apply the installed preset for {name}")
        locked = tomllib.loads((target / "uv.lock").read_text())["package"]
        versions = {item["name"]: item["version"] for item in locked}
        if versions.get("project-presets-demo") != release or versions.get("ruff") != ruff or metadata.version("ruff") != ruff:
            raise ValueError("Sync the preset and Ruff with the uv lock before merging")
        subprocess.run(["uv", "lock", "--check"], cwd=target, check=True)
    if args.write:
        writes[manifest_path] = text.encode()
        writes[marker] = (json.dumps(state, indent=2) + "\n").encode()
        # Stage before replacement; on filesystem failure keep files for recovery.
        staged = []
        for destination, content in writes.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".preset-new")
            with temporary.open("xb") as file:
                file.write(content)
            staged.append((temporary, destination))
        for temporary, destination in staged:
            temporary.replace(destination)
        if args.sync:
            subprocess.run(["uv", "sync", "--locked"], cwd=target, check=True)
