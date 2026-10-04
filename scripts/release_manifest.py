"""Shared publication tags, profile versions and immutable artifact names."""

import re

PROFILES = ("typescript-node", "typescript-hono", "typescript-next", "python-scripts", "python-django", "python-fastapi")


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
