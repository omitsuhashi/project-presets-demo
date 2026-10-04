"""Command-line interface for applying Python profiles."""

import argparse
import importlib.metadata as metadata
import subprocess

from .project import apply


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=["python-scripts", "python-django", "python-fastapi"])
    parser.add_argument("directory", nargs="?", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--setup", action="store_true", help="Apply settings and install all profile dependencies")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--adopt", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--source", help="Override the default GitHub release wheel URL")
    args = parser.parse_args()
    args.write = args.write or args.setup
    args.sync = args.sync or args.setup
    try:
        apply(args)
    except (ValueError, OSError, metadata.PackageNotFoundError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")

