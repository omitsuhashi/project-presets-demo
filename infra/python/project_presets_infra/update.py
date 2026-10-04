"""Update managed infrastructure references while preserving consumer configuration."""

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from .config import PREFIX, PROFILES, PROVIDER, REPOSITORY, source, version
from .native import run, write_json


def update(target, requested):
    marker = target / "infra/.project-infra.json"
    state = json.loads(marker.read_text())
    current = version(state["release"])
    selected = requested
    if not selected:
        tags = run("gh", "api", f"repos/{REPOSITORY}/releases", "--paginate", "--jq",
                   ".[] | select(.draft == false and .prerelease == false) | .tag_name", capture=True).splitlines()
        available = [tag[len(PREFIX):] for tag in tags if tag.startswith(PREFIX) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", tag[len(PREFIX):])]
        available = [item for item in available if version(item)[0] == current[0] and version(item) >= current]
        if not available:
            raise ValueError("No compatible infrastructure release exists")
        selected = max(available, key=version)
    if version(selected)[0] != current[0]:
        raise ValueError("Major infrastructure upgrades need an explicit root/module migration")
    if selected != importlib.metadata.version("project-presets-infra"):
        raise ValueError("Execute the infrastructure CLI from the selected release so tooling and provider pins match")
    pending = []
    for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
        path = target / f"infra/{folder}/preset.tf.json"
        value = json.loads(path.read_text())
        reference = value["module"]["preset"]["source"]
        if reference not in {source(kind, state["release"]), source(kind, selected)}:
            raise ValueError(f"{folder}'s managed module reference was changed locally")
        value["module"]["preset"]["source"] = source(kind, selected)
        provider = value["terraform"]["required_providers"]["aws"]
        if provider.get("source") != "hashicorp/aws" or provider.get("version") not in {f"= {state['provider']}", f"= {PROVIDER}"}:
            raise ValueError(f"{folder}'s managed provider pin was changed locally")
        provider["version"] = f"= {PROVIDER}"
        pending.append((path, value))
    if not set(state["files"]).issubset({"Dockerfile", ".dockerignore"}):
        raise ValueError("Unsupported managed file in infrastructure marker")
    hashes, copied = {}, []
    templates = Path(__file__).parent / "templates"
    docker = PROFILES[state["profile"]][1]
    for name, digest in state["files"].items():
        path = target / name
        content = (templates / (f"{docker}.Dockerfile" if name == "Dockerfile" else "dockerignore")).read_bytes()
        new_digest = hashlib.sha256(content).hexdigest()
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() not in {digest, new_digest}:
            raise ValueError(f"{name} was changed or deleted locally; resolve before updating")
        hashes[name] = new_digest
        copied.append((path, content))
    for path, value in pending:
        write_json(path, value)
    for path, content in copied:
        temporary = path.with_name(path.name + ".preset-new")
        with temporary.open("xb") as file:
            file.write(content)
        temporary.replace(path)
    write_json(marker, {**state, "release": selected, "provider": PROVIDER, "files": hashes})
    print(f"Updated infrastructure {state['release']} -> {selected}; review both Terraform plans before applying")
