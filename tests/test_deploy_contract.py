from __future__ import annotations

import fnmatch
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_MANIFEST = ROOT / "deploy" / "module.manifest.json"
SERVER_MANIFEST = ROOT / "deploy" / "server.manifest.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/").strip("/")
    normalized_pattern = pattern.replace("\\", "/").strip().strip("/")
    if not normalized_pattern:
        return False
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    if any(char in normalized_pattern for char in "*?["):
        return fnmatch.fnmatchcase(normalized_path, normalized_pattern)
    return normalized_path == normalized_pattern or normalized_path.startswith(normalized_pattern + "/")


def deploy_inventory(manifest: dict) -> set[str]:
    include = manifest["include"]
    exclude = manifest["exclude"] + manifest["forbidden_paths"]
    inventory: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if not any(path_matches(relative, pattern) for pattern in include):
            continue
        if any(path_matches(relative, pattern) for pattern in exclude):
            continue
        inventory.add(relative)
    return inventory


class DeployContractTests(unittest.TestCase):
    def test_module_manifest_is_canonical_and_complete(self):
        manifest = load_json(MODULE_MANIFEST)

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["module"], "backupkit")
        self.assertTrue(manifest["include"])

        for field in ("include", "exclude", "required_paths", "forbidden_paths"):
            self.assertIsInstance(manifest[field], list)
            self.assertTrue(all(isinstance(value, str) and value for value in manifest[field]))

        for required in manifest["required_paths"]:
            self.assertTrue((ROOT / required).exists(), required)

    def test_module_inventory_contains_runtime_and_excludes_state(self):
        manifest = load_json(MODULE_MANIFEST)
        inventory = deploy_inventory(manifest)

        expected = {
            "module.php",
            "back/bootstrap.php",
            "bin/backupkit",
            "core/cli.py",
            "core/result.py",
            "core/backup.py",
            "adapters/mysql/adapter.py",
        }
        self.assertTrue(expected.issubset(inventory), sorted(expected - inventory))

        forbidden_prefixes = (
            ".git/",
            ".github/",
            "docs/",
            "tests/",
            "examples/",
            "scripts/",
            "var/",
            "releases/",
        )
        for path in inventory:
            self.assertFalse(path.startswith(forbidden_prefixes), path)
            self.assertNotIn("/__pycache__/", f"/{path}")
            self.assertFalse(path.endswith((".pyc", ".log", ".zip")), path)
            self.assertFalse(Path(path).name.startswith(".env"), path)

    def test_server_manifest_matches_standalone_tooling_contract(self):
        module_manifest = load_json(MODULE_MANIFEST)
        manifest = load_json(SERVER_MANIFEST)

        self.assertEqual(manifest["project"], "BackupKit")
        self.assertEqual(manifest["profile"], "server")
        self.assertEqual(manifest["zip_prefix"], "backupkit-server")
        self.assertFalse(manifest["requires_public_html_in_zip"])
        self.assertEqual(manifest["submodules"], {})
        self.assertEqual(manifest["include"], module_manifest["include"])
        self.assertEqual(manifest["required_paths"], module_manifest["required_paths"])

        inventory = deploy_inventory(manifest)
        self.assertIn("bin/backupkit", inventory)
        self.assertIn("core/backup.py", inventory)
        self.assertFalse(any(path.startswith("public_html/") for path in inventory))
        self.assertFalse(any(path.endswith((".sql", ".sql.gz", ".dump", ".bak")) for path in inventory))

    def test_runtime_configuration_is_not_packaged(self):
        manifest = load_json(SERVER_MANIFEST)
        inventory = deploy_inventory(manifest)

        forbidden_names = {".env", ".env.backup", "backup.policy.yml", "restore-test.policy.yml"}
        self.assertTrue(forbidden_names.isdisjoint({Path(path).name for path in inventory}))
        self.assertFalse(any(path.startswith("var/") for path in inventory))


if __name__ == "__main__":
    unittest.main()
