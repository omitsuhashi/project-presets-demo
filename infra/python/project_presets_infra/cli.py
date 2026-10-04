"""Command-line routing for the infrastructure preset."""

import argparse
import json
import subprocess
from pathlib import Path

from .bootstrap import bootstrap
from .config import PROFILES, source
from .deploy import container_check, deploy, plan
from .native import foundation_plan, identity, tf
from .scaffold import init
from .update import update


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "check", "container-check", "bootstrap", "plan", "deploy", "update"])
    parser.add_argument("--directory", default=".")
    parser.add_argument("--name")
    parser.add_argument("--repository")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--version")
    parser.add_argument("--apply", action="store_true", help="Authorize AWS resource creation during bootstrap")
    args = parser.parse_args()
    target = Path(args.directory).resolve()
    try:
        if args.command == "init":
            init(target, args)
        elif args.command == "bootstrap":
            bootstrap(target, args.apply)
        elif args.command == "container-check":
            container_check(target)
        elif args.command == "deploy":
            deploy(target)
        elif args.command == "plan":
            identity(target)
            foundation_plan(target)
            plan(target)
        elif args.command == "update":
            update(target, args.version)
        else:
            state = json.loads((target / "infra/.project-infra.json").read_text())
            for folder, kind in [("foundation", "aws-foundation"), ("app", "aws-container-service")]:
                path = target / f"infra/{folder}"
                value = json.loads((path / "preset.tf.json").read_text())
                if value["module"]["preset"]["source"] != source(kind, state["release"]):
                    raise ValueError("Apply the pinned module reference")
                provider = value["terraform"]["required_providers"]["aws"]
                if provider.get("source") != "hashicorp/aws" or provider.get("version") != f"= {state['provider']}":
                    raise ValueError("Apply the managed provider pin")
                tf(path, "init", "-upgrade", "-backend=false", "-input=false")
                tf(path, "validate")
    except (OSError, ValueError, KeyError, AssertionError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
