"""Compute a Python preset update without filesystem or process access."""

import hashlib
import re
from dataclasses import dataclass

import tomllib


def requirement_name(requirement):
    return re.split(r"[^a-z0-9_-]", requirement.lower().strip(), maxsplit=1)[0].replace("_", "-")


@dataclass
class Plan:
    summary: dict
    state: dict
    writes: dict
    commands: list
    manifest_text: str
    manifest_suffix: str
    initialize: bool

    @property
    def versions(self):
        return {"project-presets-demo": self.state["release"],
                **self.state["devDependencies"], **self.state.get("dependencies", {})}


def plan_update(project, preset, *, profile, adopt=False, source=None, check=False):
    if source is not None and not re.match(r"^(https?://|file://)", source):
        raise ValueError("--source must be a wheel URL")
    previous = project["previous"]
    initialize = project["manifest_text"] is None
    if initialize and previous:
        raise ValueError("pyproject.toml was deleted locally; restore it before updating")
    if initialize and check:
        raise ValueError("Run --setup to create pyproject.toml and apply this preset")
    name = re.sub(r"[^a-z0-9._-]+", "-", project["name"].lower()).strip("._-") or "project"
    text = (f'[project]\nname = "{name}"\nversion = "0.0.0"\nrequires-python = ">=3.12,<3.13"\ndependencies = []\n'
            if initialize else project["manifest_text"])
    manifest = tomllib.loads(text)
    if "project" not in manifest:
        raise ValueError("pyproject.toml must define [project]; add project metadata before applying the preset")
    preset_version = preset["version"]
    publication = preset["publication"]
    if publication and (publication["profile"] != profile or publication["version"] != preset_version):
        raise ValueError("The artifact does not match the selected template/version")
    publication_tag = publication["tag"] if publication else f"v{preset_version}"
    requirements = preset["requirements"]
    ruff = next(item.removeprefix("ruff==") for item in requirements if item.startswith("ruff=="))
    base = "https://github.com/omitsuhashi/project-presets-demo/releases/download/"
    filename = publication["asset"] if publication else f"project_presets_demo-{preset_version}-py3-none-any.whl"
    artifact = source or f"{base}{publication_tag}/{filename}"
    dev = manifest.get("dependency-groups", {}).get("dev", [])
    has_preset = any(isinstance(item, str) and requirement_name(item) == "project-presets-demo" for item in dev)
    preset_source = manifest.get("tool", {}).get("uv", {}).get("sources", {}).get("project-presets-demo", {})
    public_source = isinstance(preset_source, dict) and preset_source.get("url", "").startswith(base)
    install_preset = bool(source) or not has_preset or public_source
    if any(requirement_name(item) == "project-presets-demo" for item in manifest["project"].get("dependencies", [])):
        raise ValueError("The preset package must be a dev dependency")
    kind = profile.removeprefix("python-")
    dependencies = {}
    for requirement in requirements:
        match = re.fullmatch(r"([a-z0-9-]+)==([0-9.]+)\s*;\s*extra == ['\"]([a-z]+)['\"]", requirement)
        if match and match[3] == kind:
            dependencies[match[1]] = match[2]
    if kind != "scripts" and not dependencies:
        raise ValueError("The installed wheel is missing framework dependency pins")
    if previous and previous["profile"] != profile:
        raise ValueError("Changing profiles requires an application migration")
    if previous and set(previous.get("dependencies", {})) - set(dependencies):
        raise ValueError("Removing managed dependencies requires an application migration")
    if project["legacy_submodule"]:
        raise ValueError("Remove the old preset submodule in a reviewed migration before adopting the wheel")
    config = manifest.get("tool", {}).get("ruff")
    if previous and config is None:
        raise ValueError("Ruff configuration was deleted locally; restore before updating")
    extend = f".project-presets/ruff/{kind}.toml"
    if config is not None:
        if config.get("extend") != extend or (not previous and not adopt):
            raise ValueError(f"Integrate [tool.ruff] extend = {extend!r}, then use --adopt to preserve existing settings")
    for name, version in dependencies.items():
        current = [item.lower().strip() for item in manifest["project"].get("dependencies", [])
                   if requirement_name(item) == name]
        old = (previous or {}).get("dependencies", {}).get(name)
        if current and current not in ([f"{name}=={version}"], [f"{name}=={old}"]):
            raise ValueError(f"{name} was changed locally; integrate its exact pin before adopting or updating")
        if old and not current:
            raise ValueError(f"{name} was deleted locally; restore before updating")
    writes = {}
    hashes = {}
    for filename, content in sorted(preset["configs"].items()):
        name = f".project-presets/ruff/{filename}"
        hashes[name] = hashlib.sha256(content).hexdigest()
        if name in project["files"]:
            current = hashlib.sha256(project["files"][name]).hexdigest()
            if current != hashes[name] and current != (previous or {}).get("files", {}).get(name):
                raise ValueError(f"{name} was changed locally; resolve before updating")
        elif name in (previous or {}).get("files", {}):
            raise ValueError(f"{name} was deleted locally; restore before updating")
        writes[name] = content
    if previous and set(previous["files"]) - set(hashes):
        raise ValueError("Removing managed configuration requires a migration")
    workflow = ".github/workflows/update-presets.yml"
    if workflow not in project["files"]:
        writes[workflow] = preset["workflow"].replace("PRESET_TAG", publication_tag).encode()
    state = {"profile": profile, "release": preset_version, "files": hashes, "devDependencies": {"ruff": ruff}}
    if dependencies:
        state["dependencies"] = dependencies
    create = (["pyproject.toml"] if initialize else []) + ([workflow] if workflow not in project["files"] else [])
    summary = {"profile": profile, "release": preset_version, "source": artifact if install_preset else preset_source,
               "ruff": ruff, "dependencies": dependencies, "files": list(hashes), "create": create}
    commands = []
    if install_preset:
        commands.append(["uv", "add", "--dev", "--no-sync", f"project-presets-demo @ {artifact}"])
    if dependencies:
        commands.append(["uv", "add", "--no-sync", *(f"{name}=={version}" for name, version in dependencies.items())])
    suffix = f'\n[tool.ruff]\nextend = "{extend}"\ntarget-version = "py312"\n' if config is None else ""
    return Plan(summary, state, writes, commands, text, suffix, initialize)
