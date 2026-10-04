"""Planning contracts, independent of installed packages and external commands."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from project_presets_demo.plan import plan_update

PRESET = {
    "version": "2.2.1",
    "publication": {"profile": "python-fastapi", "version": "2.2.1", "tag": "v2.3.0", "asset": "fastapi.whl"},
    "requirements": ["ruff==0.16.10", "fastapi==0.142.2; extra == 'fastapi'", "uvicorn==0.54.0; extra == 'fastapi'"],
    "configs": {"base.toml": b'[lint]\nselect = ["F"]\n', "fastapi.toml": b'extend = "base.toml"\n'},
    "workflow": "uses: update-consumer.yml@PRESET_TAG\n",
}


def empty():
    return {"name": "My project", "manifest_text": None, "previous": None, "files": {}, "legacy_submodule": False}


def adopted():
    initial = plan_update(empty(), PRESET, profile="python-fastapi")
    project = empty()
    project["manifest_text"] = '''# project comment
[project]
name = "existing"
version = "0.0.0"
dependencies = ["fastapi==0.142.2", "uvicorn==0.54.0", "project-library>=1"]
[dependency-groups]
dev = ["project-presets-demo"]
[tool.uv.sources]
project-presets-demo = { path = "../presets", editable = true }
[tool.ruff]
extend = ".project-presets/ruff/fastapi.toml"
line-length = 110
'''
    project["previous"] = copy.deepcopy(initial.state)
    project["files"] = copy.deepcopy(initial.writes)
    return project


class PresetPlanTests(unittest.TestCase):
    def test_new_project_plan_has_no_side_effects_and_distinguishes_versions(self):
        project = empty()
        before = copy.deepcopy(project)
        plan = plan_update(project, PRESET, profile="python-fastapi")
        self.assertEqual(project, before)
        self.assertEqual(plan, plan_update(project, PRESET, profile="python-fastapi"))
        self.assertEqual(plan.summary["release"], "2.2.1")
        self.assertEqual(plan.summary["source"], "https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.3.0/fastapi.whl")
        self.assertIn(b"@v2.3.0", plan.writes[".github/workflows/update-presets.yml"])
        self.assertIn('name = "my-project"', plan.manifest_text)
        self.assertEqual(plan.commands[-1], ["uv", "add", "--no-sync", "fastapi==0.142.2", "uvicorn==0.54.0"])

    def test_existing_settings_comments_and_custom_source_are_preserved(self):
        project = adopted()
        plan = plan_update(project, PRESET, profile="python-fastapi")
        self.assertEqual(plan.manifest_text, project["manifest_text"])
        self.assertEqual(plan.manifest_suffix, "")
        self.assertEqual(plan.summary["source"], {"path": "../presets", "editable": True})
        self.assertEqual(len(plan.commands), 1)
        self.assertNotIn(".github/workflows/update-presets.yml", plan.writes)
        self.assertEqual(plan.state, project["previous"])

    def test_update_accepts_old_managed_pins_without_mutating_snapshot(self):
        project = adopted()
        project["manifest_text"] = project["manifest_text"].replace("fastapi==0.142.2", "fastapi==0.142.1")
        project["previous"]["dependencies"]["fastapi"] = "0.142.1"
        before = copy.deepcopy(project)
        plan = plan_update(project, PRESET, profile="python-fastapi")
        self.assertEqual(project, before)
        self.assertEqual(plan.state["dependencies"]["fastapi"], "0.142.2")
        self.assertIn("project-library>=1", plan.manifest_text)

    def test_managed_dependency_changes_and_deletions_are_rejected(self):
        project = adopted()
        project["manifest_text"] = project["manifest_text"].replace("fastapi==0.142.2", "fastapi>=1")
        with self.assertRaisesRegex(ValueError, "fastapi was changed locally"):
            plan_update(project, PRESET, profile="python-fastapi")
        project["manifest_text"] = project["manifest_text"].replace('"fastapi>=1", ', '')
        with self.assertRaisesRegex(ValueError, "fastapi was deleted locally"):
            plan_update(project, PRESET, profile="python-fastapi")

    def test_managed_config_changes_and_deletions_are_rejected(self):
        project = adopted()
        name = ".project-presets/ruff/base.toml"
        project["files"][name] = b"# local override\n"
        with self.assertRaisesRegex(ValueError, "changed locally"):
            plan_update(project, PRESET, profile="python-fastapi")
        del project["files"][name]
        with self.assertRaisesRegex(ValueError, "deleted locally"):
            plan_update(project, PRESET, profile="python-fastapi")

    def test_adoption_requires_explicit_consent(self):
        project = adopted()
        project["previous"] = None
        with self.assertRaisesRegex(ValueError, "use --adopt"):
            plan_update(project, PRESET, profile="python-fastapi")
        plan = plan_update(project, PRESET, profile="python-fastapi", adopt=True)
        self.assertEqual(plan.manifest_suffix, "")

    def test_wrong_artifact_and_missing_manifest_fail_before_application(self):
        with self.assertRaisesRegex(ValueError, "artifact does not match"):
            plan_update(empty(), PRESET, profile="python-django")
        with self.assertRaisesRegex(ValueError, "Run --setup"):
            plan_update(empty(), PRESET, profile="python-fastapi", check=True)


if __name__ == "__main__":
    unittest.main()
