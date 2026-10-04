"""Infrastructure profile identities and immutable module references."""

import re

REPOSITORY = "omitsuhashi/project-presets-demo"
PREFIX = "infra-aws-container-v"
PROVIDER = "6.67.0"
PROFILES = {"typescript-hono": (3000, "hono"), "python-fastapi": (8000, "fastapi")}


def version(value):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Use a stable infrastructure version, for example 1.0.0")
    return tuple(map(int, value.split(".")))


def source(kind, release):
    version(release)
    return f"git::https://github.com/{REPOSITORY}.git//infra/modules/{kind}?ref={PREFIX}{release}"
