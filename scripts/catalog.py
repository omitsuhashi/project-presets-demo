"""Generate pinned catalogs from profile roles and native package manifests."""

import argparse
import json
import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def resolve(root=ROOT):
    definitions = json.loads((root / "profiles/definitions.json").read_text())
    npm = json.loads((root / "package.json").read_text())
    python = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    pins = {"typescript": npm["dependencies"] | npm["devDependencies"], "python": {}}
    requirements = python["dependencies"] + [item for group in python["optional-dependencies"].values() for item in group]
    for requirement in requirements:
        match = re.fullmatch(r"([a-z0-9-]+)==([0-9.]+)", requirement)
        if not match:
            raise ValueError(f"Use an exact Python dependency pin: {requirement}")
        if match[1] in pins["python"] and pins["python"][match[1]] != match[2]:
            raise ValueError(f"Conflicting Python pins: {match[1]}")
        pins["python"][match[1]] = match[2]
    catalog = {}
    for name, definition in definitions.items():
        profile = dict(definition)
        for field in ("dependencies", "devDependencies"):
            if field in profile:
                profile[field] = {dependency: pins[profile["language"]][dependency] for dependency in definition[field]}
        catalog[name] = profile
    return catalog


def outputs(root=ROOT):
    catalog = resolve(root)
    return {"profiles.json": json.dumps({name: item for name, item in catalog.items() if item["language"] == "typescript"}, indent=2) + "\n",
            "python/profiles.json": json.dumps({name: item for name, item in catalog.items() if item["language"] == "python"}, indent=2) + "\n",
            "profiles/python-scripts/requirements-dev.txt": "ruff==" + catalog["python-scripts"]["devDependencies"]["ruff"] + "\n"}


def generate(root=ROOT):
    for name, content in outputs(root).items():
        (root / name).write_text(content)


def check(root=ROOT):
    for name, content in outputs(root).items():
        path = root / name
        current = path.read_text() if path.exists() else ""
        matches = json.loads(current) == json.loads(content) if name.endswith(".json") and current else current == content
        if not matches:
            raise ValueError(f"Generated catalog differs: {name}; run scripts/catalog.py generate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "check"])
    args = parser.parse_args()
    if args.command == "generate":
        generate()
    else:
        check()


if __name__ == "__main__":
    main()
