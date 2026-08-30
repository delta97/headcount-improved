"""Edge-case tests for the canonical registry (scripts/registry.py) and the cross-consistency
check (scripts/validate-catalog.py), against throwaway fixture trees.

Every failure asserted here is a drift the real tree cannot demonstrate while healthy —
which is exactly why each needs a fixture: the catalog check exists for states the
repository should never be in.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
VALIDATOR = os.path.join(SCRIPTS, "validate-catalog.py")
MARKETPLACE = os.path.join(SCRIPTS, "build-marketplace.py")

OWNER = {"name": "Chris Brock"}
REPO_URL = "https://github.com/cbrock84/headcount"


def dept(ident, category, rank, reviewer=False, **over):
    d = {
        "id": ident, "title": ident.title(), "executive": "Chief", "rank": rank,
        "category": category, "reviewer_class": reviewer,
        "description": f"A description of the {ident} department long enough to pass the thinness check.",
        "version": "1.0.0", "keywords": [ident],
    }
    d.update(over)
    return d


def registry_doc(depts):
    return {
        "marketplace": {"name": "headcount", "owner": OWNER,
                        "description": "Fixture marketplace description.", "version": "1.0.0"},
        "departments": depts,
    }


def manifest(d):
    return {"name": d["id"], "description": d["description"], "version": d["version"],
            "author": OWNER, "repository": REPO_URL, "keywords": d["keywords"]}


SURFACE_MAP = """# fixture map
```roster
technology         builder    installed
security           builder    installed
security-review    reviewer   installed
```
"""


def write_tree(root, tree):
    for rel, content in tree.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, indent=2))


def happy_tree():
    depts = [dept("technology", "technology", 10),
             dept("security", "security", 20, reviewer=True)]
    tree = {"config/departments.json": registry_doc(depts), "docs/AGENT-SURFACES.md": SURFACE_MAP}
    for d in depts:
        tree[f"plugins/{d['id']}/.claude-plugin/plugin.json"] = manifest(d)
        tree[f".claude/agents/{d['id']}.md"] = f"# {d['id']}\n"
    return tree


def run_catalog(tree, generate_marketplace=True):
    with tempfile.TemporaryDirectory() as root:
        write_tree(root, tree)
        if generate_marketplace:
            subprocess.run([sys.executable, MARKETPLACE], cwd=root, capture_output=True)
        proc = subprocess.run([sys.executable, VALIDATOR], cwd=root,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


def run_registry_load(registry_content):
    with tempfile.TemporaryDirectory() as root:
        write_tree(root, {"config/departments.json": registry_content})
        proc = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {SCRIPTS!r}); import registry; registry.load()"],
            cwd=root, capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


class RegistryLoadTest(unittest.TestCase):
    def test_valid_registry_loads(self):
        code, out = run_registry_load(registry_doc([dept("technology", "technology", 10)]))
        self.assertEqual(code, 0, out)

    def test_duplicate_id_fails(self):
        code, out = run_registry_load(registry_doc(
            [dept("technology", "technology", 10), dept("technology", "technology", 20)]))
        self.assertNotEqual(code, 0)
        self.assertIn("duplicate department id", out)

    def test_duplicate_rank_fails(self):
        code, out = run_registry_load(registry_doc(
            [dept("technology", "technology", 10), dept("security", "security", 10)]))
        self.assertNotEqual(code, 0)
        self.assertIn("duplicate rank", out)

    def test_missing_field_fails(self):
        broken = dept("technology", "technology", 10)
        del broken["executive"]
        code, out = run_registry_load(registry_doc([broken]))
        self.assertNotEqual(code, 0)
        self.assertIn("missing field(s): executive", out)

    def test_unknown_field_fails(self):
        code, out = run_registry_load(registry_doc([dept("technology", "technology", 10, extra="x")]))
        self.assertNotEqual(code, 0)
        self.assertIn("unknown field(s): extra", out)

    def test_bool_rank_fails(self):
        code, out = run_registry_load(registry_doc([dept("technology", "technology", True)]))
        self.assertNotEqual(code, 0)
        self.assertIn("rank must be int", out)


class ValidateCatalogTest(unittest.TestCase):
    def test_consistent_tree_passes(self):
        code, out = run_catalog(happy_tree())
        self.assertEqual(code, 0, out)

    def test_plugin_without_registry_entry_fails(self):
        tree = happy_tree()
        tree["plugins/mystery/.claude-plugin/plugin.json"] = manifest(dept("mystery", "technology", 30))
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("plugins/mystery/ exists but has no registry entry", out)

    def test_registry_entry_without_plugin_fails(self):
        tree = happy_tree()
        doc = tree["config/departments.json"]
        doc["departments"].append(dept("phantom", "technology", 30))
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("plugins/phantom/ does not exist", out)

    def test_manifest_description_drift_fails(self):
        tree = happy_tree()
        man = tree["plugins/technology/.claude-plugin/plugin.json"]
        man["description"] = "A quietly different description, the drift this check exists to catch."
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("description disagrees with the registry", out)

    def test_bad_semver_fails(self):
        tree = happy_tree()
        tree["config/departments.json"]["departments"][0]["version"] = "1.0"
        tree["plugins/technology/.claude-plugin/plugin.json"]["version"] = "1.0"
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("not MAJOR.MINOR.PATCH", out)

    def test_unknown_category_fails(self):
        tree = happy_tree()
        tree["config/departments.json"]["departments"][0]["category"] = "sorcery"
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("not a known category", out)

    def test_stale_marketplace_fails(self):
        tree = happy_tree()
        tree[".claude-plugin/marketplace.json"] = {
            "name": "headcount", "owner": OWNER,
            "metadata": {"description": "x", "version": "1.0.0"},
            "plugins": [{"name": "technology", "source": "./plugins/technology"}],
        }
        code, out = run_catalog(tree, generate_marketplace=False)
        self.assertEqual(code, 1)
        self.assertIn("plugin set differs from the registry", out)

    def test_marketplace_source_must_exist(self):
        tree = happy_tree()
        tree[".claude-plugin/marketplace.json"] = {
            "name": "headcount", "owner": OWNER,
            "metadata": {"description": "x", "version": "1.0.0"},
            "plugins": [{"name": "technology", "source": "./plugins/nowhere"},
                        {"name": "security", "source": "./plugins/security"}],
        }
        code, out = run_catalog(tree, generate_marketplace=False)
        self.assertEqual(code, 1)
        self.assertIn("does not exist", out)

    def test_missing_roster_row_fails(self):
        tree = happy_tree()
        tree["docs/AGENT-SURFACES.md"] = SURFACE_MAP.replace("technology         builder    installed\n", "")
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("'technology' has no roster row", out)

    def test_reviewer_class_needs_review_row(self):
        tree = happy_tree()
        tree["docs/AGENT-SURFACES.md"] = SURFACE_MAP.replace(
            "security-review    reviewer   installed\n", "")
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn("reviewer-class but has no 'security-review' reviewer row", out)

    def test_missing_charter_fails(self):
        tree = happy_tree()
        del tree[".claude/agents/security.md"]
        code, out = run_catalog(tree)
        self.assertEqual(code, 1)
        self.assertIn(".claude/agents/security.md is missing", out)


class BuildMarketplaceTest(unittest.TestCase):
    def test_check_detects_staleness_and_regeneration_fixes_it(self):
        with tempfile.TemporaryDirectory() as root:
            write_tree(root, happy_tree())
            check = subprocess.run([sys.executable, MARKETPLACE, "--check"], cwd=root,
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 1)
            self.assertIn("stale", check.stdout)
            subprocess.run([sys.executable, MARKETPLACE], cwd=root, capture_output=True, check=True)
            check = subprocess.run([sys.executable, MARKETPLACE, "--check"], cwd=root,
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
