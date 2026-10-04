"""Project-owned helper. Standard Terraform/Docker commands remain usable directly."""

import argparse
import subprocess
from pathlib import Path

from bootstrap import bootstrap
from deploy import container_check, deploy, plan
from native import foundation_plan, identity, tf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "container-check", "bootstrap", "plan", "deploy"])
    parser.add_argument("--apply", action="store_true", help="Authorize AWS resource creation during bootstrap")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[2]
    try:
        if args.command == "bootstrap":
            bootstrap(target, args.apply)
        elif args.command == "container-check":
            container_check(target)
        elif args.command == "deploy":
            deploy(target)
        elif args.command == "plan":
            identity(target)
            foundation_plan(target)
            plan(target)
        else:
            for folder in ["foundation", "app"]:
                path = target / "infra" / folder
                tf(path, "init", "-backend=false", "-input=false")
                tf(path, "validate")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
