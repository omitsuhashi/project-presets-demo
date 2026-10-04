"""Generate an initial AWS recipe; generated files are maintained by the project."""

import argparse
from pathlib import Path

from .config import PROFILES
from .scaffold import init


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init"])
    parser.add_argument("--directory", default=".")
    parser.add_argument("--name")
    parser.add_argument("--repository")
    parser.add_argument("--region")
    parser.add_argument("--branch")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--module-version", help="Fixed published module version for new infrastructure; defaults to this recipe's version")
    parser.add_argument("--adopt", action="store_true", help="Keep v1 Terraform/Docker files; replace legacy preset workflows with project-owned files")
    args = parser.parse_args()
    try:
        init(Path(args.directory).resolve(), args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
