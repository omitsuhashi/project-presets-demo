"""Prepare one release index and build only templates whose inputs changed."""

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ("typescript-node", "typescript-hono", "typescript-next", "python-scripts", "python-django", "python-fastapi")


def npm_dependencies(package, profile):
    return {name: pin for name, pin in package["dependencies"].items()
            if profile != "typescript-next" or name not in {"@eslint/js", "globals", "typescript-eslint"}}


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value):
        raise ValueError("Use a stable version such as 2.2.0")
    return tuple(map(int, value.split(".")))


def asset(profile, release):
    version(release)
    if profile not in PROFILES:
        raise ValueError(f"Unsupported profile: {profile}")
    return (f"{profile}-{release}.tgz" if profile.startswith("typescript-")
            else f"project_presets_demo-{release}-1{profile.removeprefix('python-')}-py3-none-any.whl")


def validate(index):
    version(index["tag"].removeprefix("v"))
    if not index["tag"].startswith("v") or set(index["profiles"]) != set(PROFILES):
        raise ValueError("A release index must have one vX.Y.Z tag and all six templates")
    for profile, entry in index["profiles"].items():
        version(entry["tag"].removeprefix("v"))
        if (not entry["tag"].startswith("v") or version(entry["tag"][1:]) > version(index["tag"][1:])
                or entry["asset"] != asset(profile, entry["version"])
                or not re.fullmatch(r"[a-f0-9]{64}", entry["fingerprint"])):
            raise ValueError(f"Invalid release entry: {profile}")
    return index


def fingerprints(root=ROOT):
    npm = json.loads((root / "package.json").read_text())
    python = tomllib.loads((root / "pyproject.toml").read_text())
    catalog = json.loads((root / "profiles.json").read_text()) | json.loads((root / "python/profiles.json").read_text())
    result = {}
    for profile in PROFILES:
        descriptor = catalog[profile]
        files = ["scripts/release_presets.py", "scripts/update-consumer.py", ".github/workflows/update-consumer.yml",
                 "python/project_presets_demo/update-presets.yml"]
        if profile.startswith("typescript-"):
            kind = descriptor["tsconfig"]
            files += ["scripts/apply-profile.mjs", f"typescript/tsconfig-{kind}.json", f"typescript/{kind}.js"]
            if kind == "node":
                files += ["typescript/base.js"]
            native = {key: npm[key] for key in ("name", "dependencies", "engines", "packageManager")}
            native["dependencies"] = npm_dependencies(npm, profile)
            if kind == "next":
                native["peerDependencies"] = npm["peerDependencies"]
        else:
            files += ["python/project_presets_demo/__init__.py"]
            config = root / "python/project_presets_demo/config" / (profile.removeprefix("python-") + ".toml")
            while True:
                files.append(str(config.relative_to(root)))
                extend = tomllib.loads(config.read_text()).get("extend")
                if not extend:
                    break
                config = config.parent / extend
            native = {"requires-python": python["project"]["requires-python"], "dependencies": python["project"]["dependencies"],
                      "build-system": python["build-system"], "scripts": python["project"]["scripts"]}
            kind = profile.removeprefix("python-")
            native["framework"] = python["project"].get("optional-dependencies", {}).get(kind, [])
            expected = [f"{name}=={pin}" for name, pin in descriptor.get("dependencies", {}).items()]
            if native["framework"] != expected or native["dependencies"] != ["ruff==" + descriptor["devDependencies"]["ruff"]]:
                raise ValueError(f"Catalog and Python package pins differ: {profile}")
        inputs = {"profile": descriptor, "native": native,
                  "files": {name: (root / name).read_text() for name in sorted(files)}}
        result[profile] = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return result


def prepare(root, tag, bump="patch"):
    version(tag.removeprefix("v"))
    if not tag.startswith("v"):
        raise ValueError("Use one publication tag: vX.Y.Z")
    path = root / "release-manifest.json"
    previous = validate(json.loads(path.read_text())) if path.exists() else None
    current = fingerprints(root)
    changed = [profile for profile in PROFILES if not previous or previous["profiles"][profile]["fingerprint"] != current[profile]]
    if not changed:
        return []
    if previous and version(tag[1:]) <= version(previous["tag"][1:]):
        raise ValueError("The publication tag must increase")
    entries = dict(previous["profiles"]) if previous else {}
    initial = json.loads((root / "package.json").read_text())["version"]
    for profile in changed:
        release = initial
        if previous:
            parts = list(version(entries[profile]["version"]))
            position = {"major": 0, "minor": 1, "patch": 2}[bump]
            parts[position] += 1
            parts[position + 1:] = [0] * (2 - position)
            release = ".".join(map(str, parts))
        entries[profile] = {"version": release, "tag": tag, "asset": asset(profile, release), "fingerprint": current[profile]}
    index = validate({"tag": tag, "profiles": entries})
    path.write_text(json.dumps(index, indent=2) + "\n")
    return changed


def check(root=ROOT, tag=None):
    index = validate(json.loads((root / "release-manifest.json").read_text()))
    if tag and index["tag"] != tag:
        raise ValueError("Git tag differs from release-manifest.json")
    if {name: entry["fingerprint"] for name, entry in index["profiles"].items()} != fingerprints(root):
        raise ValueError("Template inputs changed; run release_presets.py prepare with the next publication tag")
    if not any(entry["tag"] == index["tag"] for entry in index["profiles"].values()):
        raise ValueError("There are no templates to publish")
    return index


def build(root, destination):
    index = check(root)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("Build into an empty directory to avoid publishing stale artifacts")
    for profile, entry in index["profiles"].items():
        if entry["tag"] != index["tag"]:
            continue
        with tempfile.TemporaryDirectory(prefix="preset-build-") as temporary:
            stage = Path(temporary)
            for name in ("package.json", "pyproject.toml", "README.md", "LICENSE", "profiles.json", "typescript", "python", "scripts"):
                source = root / name
                if source.is_dir():
                    shutil.copytree(source, stage / name, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(source, stage / name)
            metadata = {"profile": profile, **entry}
            if profile.startswith("typescript-"):
                package = json.loads((stage / "package.json").read_text())
                package["version"] = entry["version"]
                package["dependencies"] = npm_dependencies(package, profile)
                descriptor = json.loads((stage / "profiles.json").read_text())[profile]
                kind = descriptor["tsconfig"]
                package["files"] = [f"typescript/{kind}.js", f"typescript/tsconfig-{kind}.json", "./profiles.json",
                                    "scripts/apply-profile.mjs", "python/project_presets_demo/update-presets.yml", "preset-release.json"]
                if kind == "node":
                    package["files"].append("typescript/base.js")
                package["exports"] = {".": f"./typescript/{kind}.js", f"./{descriptor['eslint']}": f"./typescript/{kind}.js",
                                      f"./tsconfig/{kind}.json": f"./typescript/tsconfig-{kind}.json"}
                package.pop("devDependencies", None)
                package.pop("scripts", None)
                if profile != "typescript-next":
                    package.pop("peerDependencies", None)
                    package.pop("peerDependenciesMeta", None)
                (stage / "package.json").write_text(json.dumps(package))
                catalog = json.loads((stage / "profiles.json").read_text())
                (stage / "profiles.json").write_text(json.dumps({profile: catalog[profile]}))
                (stage / "preset-release.json").write_text(json.dumps(metadata))
                subprocess.run(["node", str(root / "node_modules/pnpm/bin/pnpm.mjs"), "pack", "--config.ignore-scripts=true", "--pack-destination", str(stage / "dist")], cwd=stage, check=True)
                shutil.copy2(stage / "dist" / f"project-presets-demo-{entry['version']}.tgz", destination / entry["asset"])
            else:
                text = (stage / "pyproject.toml").read_text()
                text = re.sub(r'^version = "[^"]+"', f'version = "{entry["version"]}"', text, count=1, flags=re.MULTILINE)
                kind = profile.removeprefix("python-")
                extras = tomllib.loads(text)["project"]["optional-dependencies"].get(kind)
                block = "[project.optional-dependencies]\n" + (f"{kind} = {json.dumps(extras)}\n" if extras else "") + "\n"
                text = re.sub(r"\[project.optional-dependencies\]\n.*?(?=\n\[)", block, text, count=1, flags=re.DOTALL)
                (stage / "pyproject.toml").write_text(text)
                (stage / "python/project_presets_demo/release.json").write_text(json.dumps(metadata))
                subprocess.run(["uv", "build", "--wheel", "--out-dir", str(stage / "dist")], cwd=stage, check=True)
                wheel = next((stage / "dist").glob("*.whl"))
                # Standard wheel build tags distinguish templates sharing one import/package name.
                with zipfile.ZipFile(wheel) as archive:
                    contents = {name: archive.read(name) for name in archive.namelist()}
                wheel_metadata = next(name for name in contents if name.endswith(".dist-info/WHEEL"))
                contents[wheel_metadata] += f"Build: 1{profile.removeprefix('python-')}\n".encode()
                record = next(name for name in contents if name.endswith(".dist-info/RECORD"))
                rows = io.StringIO()
                writer = csv.writer(rows, lineterminator="\n")
                for name, data in contents.items():
                    if name != record:
                        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                        writer.writerow([name, f"sha256={digest}", len(data)])
                writer.writerow([record, "", ""])
                contents[record] = rows.getvalue().encode()
                with zipfile.ZipFile(destination / entry["asset"], "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, data in contents.items():
                        archive.writestr(name, data)
    shutil.copy2(root / "release-manifest.json", destination / "release-manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "check", "build"])
    parser.add_argument("--tag")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], default="patch")
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.tag:
            parser.error("prepare requires --tag")
        print("Changed templates:", ", ".join(prepare(ROOT, args.tag, args.bump)) or "none; manifest unchanged")
    elif args.command == "check":
        check(ROOT, args.tag)
    else:
        build(ROOT, args.directory.resolve())


if __name__ == "__main__":
    main()
