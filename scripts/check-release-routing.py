"""Check language release routing and unchanged-consumer behavior without network."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("updater", ROOT / "scripts/update-consumer.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def release(tag, *assets, draft=False, prerelease=False):
    return {"tag_name": tag, "assets": [{"name": name} for name in assets], "draft": draft, "prerelease": prerelease}


with tempfile.TemporaryDirectory() as directory:
    target = Path(directory)
    marker = target / ".project-preset.json"
    output = target / "output"
    for language, profile, asset in [
        ("typescript", "typescript-node", "project-presets-demo-{version}.tgz"),
        ("python", "python-scripts", "project_presets_demo-{version}-py3-none-any.whl"),
    ]:
        other = "python" if language == "typescript" else "typescript"
        state = {"profile": profile, "release": "2.1.0"}
        original = json.dumps(state).encode()
        marker.write_bytes(original)
        releases = [
            release(f"{other}-v2.9.0", asset.format(version="2.9.0")),
            release(f"{language}-v2.8.0"),  # Incomplete publication has no usable asset.
            release(f"{language}-v2.7.0", asset.format(version="2.7.0"), draft=True),
            release(f"{language}-v2.6.0", asset.format(version="2.6.0"), prerelease=True),
            release(f"{language}-v3.0.0", asset.format(version="3.0.0")),
            release("v2.1.0", asset.format(version="2.1.0")),
        ]
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                patch.object(sys, "argv", ["update-consumer", "--directory", directory]), \
                patch.object(updater.subprocess, "check_output", return_value=json.dumps([releases])), \
                patch.object(updater.subprocess, "run") as commands:
            updater.main()
            commands.assert_not_called()
        assert marker.read_bytes() == original
        assert output.read_text().endswith("changed=false\n")

        for tag, selected, requested in [
            ("v2.1.1", "2.1.1", ""),  # Unified releases remain usable.
            (f"{language}-v2.2.0", "2.2.0", ""),
            (f"{language}-v2.2.0", "2.2.0", "2.2.0"),
            (f"{language}-v2.2.0", "2.2.0", f"{language}-v2.2.0"),
        ]:
            marker.write_bytes(original)
            commands = []

            def run(command, commands=commands, state=state, selected=selected, **_kwargs):
                commands.append(command)
                marker.write_text(json.dumps({**state, "release": selected}))

            def read(command, releases=releases, tag=tag, asset=asset, selected=selected, **_kwargs):
                return (json.dumps([releases[:], [release(tag, asset.format(version=selected))]])
                        if command[0] == "gh" else "/unused/pnpm.mjs")

            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                    patch.object(sys, "argv", ["update-consumer", "--directory", directory, "--version", requested]), \
                    patch.object(updater.subprocess, "check_output", side_effect=read), \
                    patch.object(updater.subprocess, "run", side_effect=run):
                updater.main()
            url = f"https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{asset.format(version=selected)}"
            assert url in " ".join(commands[0]), commands
            assert output.read_text().endswith("changed=true\n")

    # Execute the actual release workflow's tag check with independent versions.
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    source = textwrap.dedent(workflow.split("          uv run --no-project --python 3.12 python - <<'PY'\n", 1)[1].split("          PY\n", 1)[0])
    (target / "package.json").write_text('{"version":"2.2.0"}')
    (target / "pyproject.toml").write_text('[project]\nversion="2.3.0"\n')
    for tag, success in [("typescript-v2.2.0", True), ("python-v2.3.0", True), ("python-v2.2.0", False), ("v2.2.0", False)]:
        result = subprocess.run([sys.executable, "-c", source], cwd=target, capture_output=True,
                                env={**os.environ, "GITHUB_REF_NAME": tag, "GITHUB_OUTPUT": str(output)})
        assert (result.returncode == 0) == success, result.stderr

print("PASS: independent tags, legacy releases, language/asset filtering and unchanged consumers")
