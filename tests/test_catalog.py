"""The native manifests own dependency pins; generated output rejects drift."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import catalog

ROOT = Path(__file__).resolve().parent.parent


class CatalogTests(unittest.TestCase):
    def test_native_pin_change_updates_only_profiles_that_use_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("package.json", "pyproject.toml", "profiles.json"):
                shutil.copy2(ROOT / name, root / name)
            shutil.copytree(ROOT / "profiles", root / "profiles")
            (root / "python").mkdir()
            shutil.copy2(ROOT / "python/profiles.json", root / "python/profiles.json")
            before = catalog.resolve(root)
            package = json.loads((root / "package.json").read_text())
            package["devDependencies"]["hono"] = "4.13.13"
            (root / "package.json").write_text(json.dumps(package))
            with self.assertRaisesRegex(ValueError, "Generated catalog differs"):
                catalog.check(root)
            catalog.generate(root)
            catalog.check(root)
            after = catalog.resolve(root)
            self.assertEqual({name for name in before if before[name] != after[name]}, {"typescript-hono"})
            self.assertEqual(after["typescript-hono"]["dependencies"]["hono"], "4.13.13")
            # Hand-editing generated output cannot silently become a release input.
            path = root / "profiles.json"
            edited = json.loads(path.read_text())
            edited["typescript-hono"]["dependencies"]["hono"] = "5.0.0"
            path.write_text(json.dumps(edited))
            with self.assertRaisesRegex(ValueError, "Generated catalog differs"):
                catalog.check(root)


if __name__ == "__main__":
    unittest.main()
