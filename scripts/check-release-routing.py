"""Check template versions, retained URLs and unchanged consumers without network."""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import catalog as profile_catalog
import release_presets as releases

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("updater", ROOT / "scripts/update-consumer.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def publication(index, draft=False, prerelease=False):
    assets = ["release-manifest.json"] + [entry["asset"] for entry in index["profiles"].values() if entry["tag"] == index["tag"]]
    return {"tag_name": index["tag"], "assets": [{"name": name} for name in assets], "draft": draft, "prerelease": prerelease}


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory) / "provider"
    root.mkdir()
    for name in ["package.json", "pyproject.toml", "profiles.json", "profiles", "python", "typescript", "scripts", ".github"]:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, root / name)
    assert releases.prepare(root, "v2.2.0") == list(releases.PROFILES)
    path = root / "release-manifest.json"
    baseline = json.loads(path.read_text())
    original = path.read_bytes()
    assert releases.prepare(root, "v2.3.0") == []
    assert path.read_bytes() == original
    try:
        releases.check(root, "v2.3.0")
        raise AssertionError("A different Git tag was accepted")
    except ValueError:
        pass
    package_path = root / "package.json"
    package = json.loads(package_path.read_text())
    package["devDependencies"]["hono"] = "4.13.13"
    package_path.write_text(json.dumps(package))
    profile_catalog.generate(root)
    assert releases.prepare(root, "v2.3.0") == ["typescript-hono"]
    changed = releases.check(root, "v2.3.0")
    assert changed["profiles"]["typescript-hono"]["version"] == "2.2.1"
    assert all(changed["profiles"][name] == entry for name, entry in baseline["profiles"].items() if name != "typescript-hono")
    config = root / "python/project_presets_demo/config/django.toml"
    config.write_text(config.read_text() + '\n# Django-only rule configuration\n')
    assert releases.prepare(root, "v2.4.0") == ["python-django"]
    latest = releases.check(root)
    assert latest["profiles"]["typescript-hono"] == changed["profiles"]["typescript-hono"]
    for file, expected in [("typescript/base.js", {"typescript-node", "typescript-hono"}),
                           ("typescript/next.js", {"typescript-next"}),
                           ("python/project_presets_demo/config/base.toml", {"python-scripts", "python-django", "python-fastapi"})]:
        before = releases.fingerprints(root)
        source = root / file
        content = source.read_text()
        source.write_text(content + ('\n# changed\n' if file.endswith('.toml') else '\n// changed\n'))
        after = releases.fingerprints(root)
        assert {name for name in before if before[name] != after[name]} == expected
        source.write_text(content)

    snapshots = {index["tag"]: index for index in [baseline, changed, latest]}
    published = [publication(index) for index in snapshots.values()]
    future = json.loads(json.dumps(latest))
    future["tag"] = "v3.0.0"
    future["profiles"]["typescript-hono"] = {**future["profiles"]["typescript-hono"], "version": "3.0.0", "tag": "v3.0.0", "asset": releases.asset("typescript-hono", "3.0.0")}
    snapshots[future["tag"]] = future
    published += [publication(future), publication(latest, draft=True), publication(latest, prerelease=True)]
    # Keep draft/prerelease copies distinct from the stable tag.
    published[-2]["tag_name"] = "v9.0.0"
    published[-1]["tag_name"] = "v8.0.0"
    incomplete = publication(latest)
    incomplete["tag_name"] = "v7.0.0"
    incomplete["assets"] = []
    published.append(incomplete)

    def read(command, **_kwargs):
        if command[:2] == ["gh", "api"]:
            return json.dumps([published[:2], published[2:]])
        return json.dumps(snapshots[command[3]])

    with patch.object(updater.subprocess, "check_output", side_effect=read):
        assert updater.select("typescript-hono", "2.2.0") == changed["profiles"]["typescript-hono"]
        assert updater.select("typescript-hono", "2.2.1") == {"version": "2.2.1"}
        assert updater.select("typescript-hono", "2.2.1", "2.2.0") == baseline["profiles"]["typescript-hono"]
        assert updater.select("typescript-hono", "2.2.1", "3.0.0") == future["profiles"]["typescript-hono"]
        for profile in ["typescript-node", "typescript-next", "python-scripts", "python-fastapi"]:
            target = Path(directory) / profile
            target.mkdir()
            marker = target / ".project-preset.json"
            marker.write_text(json.dumps({"profile": profile, "release": "2.2.0"}))
            content = marker.read_bytes()
            output = target / "output"
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                    patch.object(sys, "argv", ["update-consumer", "--directory", str(target)]), \
                    patch.object(updater.subprocess, "run") as commands:
                updater.main()
                commands.assert_not_called()
            assert marker.read_bytes() == content
            assert output.read_text() == "changed=false\n"
        legacy = {"tag_name": "v2.1.1", "assets": [{"name": "project-presets-demo-2.1.1.tgz"}], "draft": False, "prerelease": False}
        published.append(legacy)
        assert updater.select("typescript-node", "2.1.0", "2.1.1")["asset"] == "project-presets-demo-2.1.1.tgz"

print("PASS: template-scoped changes, one tag, retained artifact URLs, major boundaries, legacy routing and no-op consumers")
