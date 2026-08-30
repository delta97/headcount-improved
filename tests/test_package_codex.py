"""Tests for the Codex package builder (scripts/package/codex.py) and its independent
validator (scripts/package/validate.py), run against throwaway fixture trees.

The builder's whole job is a lossless, deterministic projection of the canonical tree into a
flattened layout, so the tests are about the projection's edges rather than its happy path:
determinism, the bare-name collision that a flattened runtime cannot represent (D32), carried
supporting files, and every corruption the validator exists to catch. Those states are ones the
real repository is never in, which is exactly why each needs a fixture.

Coupling to the canonical tree, kept deliberately small: a fixture repository needs only
config/departments.json, a plugins/<id>/ directory per registered department (with its skill
directories), and .claude/agents/*.md charters. The registry *loader* travels with the builder,
so a fixture supplies registry data, never a copy of scripts/registry.py.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(REPO, "scripts", "package", "codex.py")
VALIDATOR = os.path.join(REPO, "scripts", "package", "validate.py")

OWNER = {"name": "Chris Brock"}
DESC = ("Does one clearly stated thing for one clearly stated situation, described at enough "
        "length that routing can actually discriminate between neighbors.")


def dept(ident, rank):
    return {
        "id": ident, "title": ident.replace("-", " ").title(), "executive": "Chief",
        "rank": rank, "category": "operations", "reviewer_class": False,
        "description": f"A description of the {ident} department long enough to be a description.",
        "version": "1.0.0", "keywords": [ident],
    }


def registry_doc(depts):
    return {
        "marketplace": {"name": "headcount", "owner": OWNER,
                        "description": "Fixture marketplace description.", "version": "2.3.4"},
        "departments": depts,
    }


def skill_md(name):
    return f"---\nname: {name}\ndescription: {DESC}\n---\n\n# {name}\n"


def write_tree(root, tree):
    for rel, content in tree.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, indent=2))


def fixture(layout, extra=None):
    """layout: {department id: [skill names]}. Each department gets a registry entry, its skill
    directories, and a charter — the minimum the builder reads."""
    depts = [dept(ident, (i + 1) * 10) for i, ident in enumerate(sorted(layout))]
    tree = {"config/departments.json": registry_doc(depts)}
    for ident, names in layout.items():
        tree[f".claude/agents/{ident}.md"] = f"---\nname: {ident}\n---\n\n# {ident} charter\n"
        for name in names:
            tree[f"plugins/{ident}/skills/{name}/SKILL.md"] = skill_md(name)
    tree.update(extra or {})
    return tree


def make_repo(root, layout, extra=None):
    write_tree(root, fixture(layout, extra))
    return root


def run(args, cwd):
    proc = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def build(repo, out, *flags):
    return run([BUILDER, "--repo", repo, "--output", out, *flags], cwd=repo)


def validate(package, repo):
    return run([VALIDATOR, package, "--repo", repo], cwd=repo)


def read(path, mode="r"):
    with open(path, mode, **({"encoding": "utf-8"} if mode == "r" else {})) as f:
        return f.read()


def manifest_of(package):
    return json.loads(read(os.path.join(package, "headcount-package.json")))


def tree_bytes(root):
    """{relative path: bytes} for every file under root — the comparison determinism needs."""
    out = {}
    for base, _, names in os.walk(root):
        for name in names:
            path = os.path.join(base, name)
            out[os.path.relpath(path, root).replace(os.sep, "/")] = read(path, "rb")
    return out


SIMPLE = {"finance": ["unit-economics", "forecasting"], "security": ["threat-modeling"]}


class BuildLayoutTest(unittest.TestCase):
    def test_layout_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            code, log = build(repo, out)
            self.assertEqual(code, 0, log)

            for rel in ("headcount-package.json", "AGENTS.md", "README.md",
                        "agents/finance.md", "agents/security.md",
                        "skills/unit-economics/SKILL.md", "skills/forecasting/SKILL.md",
                        "skills/threat-modeling/SKILL.md"):
                self.assertTrue(os.path.exists(os.path.join(out, rel)), f"missing {rel}\n{log}")
            # Flattened, so the department directory must not survive into the package.
            self.assertFalse(os.path.exists(os.path.join(out, "skills", "finance")))

            man = manifest_of(out)
            self.assertEqual(man["format"], "headcount-package/1")
            self.assertEqual(man["runtime"], "codex")
            self.assertEqual(man["headcount_version"], "2.3.4")
            self.assertEqual(man["skill_count"], 3)
            self.assertEqual(man["agent_count"], 2)
            self.assertEqual(man["source_commit"], "unknown")
            self.assertNotIn("headcount-package.json", man["files"])
            for rel in ("AGENTS.md", "README.md", "agents/finance.md",
                        "skills/unit-economics/SKILL.md"):
                self.assertIn(rel, man["files"])

    def test_manifest_is_sorted_two_space_json_with_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            text = read(os.path.join(out, "headcount-package.json"))
            self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")

    def test_file_hashes_and_build_id_are_content_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            man = manifest_of(out)
            for rel, digest in man["files"].items():
                actual = hashlib.sha256(read(os.path.join(out, rel), "rb")).hexdigest()
                self.assertEqual(actual, digest, rel)
            expected = hashlib.sha256(
                "".join(f"{rel}\n{man['files'][rel]}\n" for rel in sorted(man["files"]))
                .encode("utf-8")).hexdigest()
            self.assertEqual(man["build_id"], expected)

    def test_charters_are_copied_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            self.assertEqual(read(os.path.join(out, "agents", "finance.md"), "rb"),
                             read(os.path.join(repo, ".claude", "agents", "finance.md"), "rb"))

    def test_supporting_files_inside_a_skill_are_carried(self):
        with tempfile.TemporaryDirectory() as tmp:
            extra = {"plugins/finance/skills/forecasting/references/method.md": "# method\n",
                     "plugins/finance/skills/forecasting/scripts/run.py": "print('x')\n"}
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE, extra)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            carried = os.path.join(out, "skills", "forecasting", "references", "method.md")
            self.assertEqual(read(carried), "# method\n")
            self.assertTrue(os.path.exists(os.path.join(out, "skills", "forecasting",
                                                        "scripts", "run.py")))
            man = manifest_of(out)
            self.assertIn("skills/forecasting/references/method.md", man["files"])
            self.assertIn("skills/forecasting/scripts/run.py", man["files"])
            # Supporting files are not skills; the count stays the number of SKILL.md files.
            self.assertEqual(man["skill_count"], 3)

    def test_generated_docs_come_from_the_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            agents_md = read(os.path.join(out, "AGENTS.md"))
            readme = read(os.path.join(out, "README.md"))
            for text in (agents_md, readme):
                self.assertIn("Finance", text)
                self.assertIn("Security", text)
                self.assertIn("Chief", text)
            self.assertIn("2.3.4", readme)


class DeterminismTest(unittest.TestCase):
    def test_two_builds_of_one_tree_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE,
                             {"plugins/finance/skills/forecasting/references/method.md": "# m\n"})
            first, second = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            self.assertEqual(build(repo, first)[0], 0)
            self.assertEqual(build(repo, second)[0], 0)
            self.assertEqual(tree_bytes(first), tree_bytes(second))
            self.assertEqual(manifest_of(first)["build_id"], manifest_of(second)["build_id"])

    def test_build_id_changes_when_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            first = os.path.join(tmp, "a")
            self.assertEqual(build(repo, first)[0], 0)
            write_tree(repo, {"plugins/security/skills/threat-modeling/SKILL.md":
                              skill_md("threat-modeling") + "\nAn added paragraph.\n"})
            second = os.path.join(tmp, "b")
            self.assertEqual(build(repo, second)[0], 0)
            self.assertNotEqual(manifest_of(first)["build_id"], manifest_of(second)["build_id"])


class CollisionTest(unittest.TestCase):
    def test_bare_name_collision_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"),
                             {"finance": ["forecasting"], "operations": ["forecasting"]})
            out = os.path.join(tmp, "pkg")
            code, log = build(repo, out)
            self.assertNotEqual(code, 0)
            self.assertIn("forecasting", log)
            self.assertIn("plugins/finance/skills/forecasting", log)
            self.assertIn("plugins/operations/skills/forecasting", log)
            self.assertIn("department:skill", log)
            self.assertIn("flattened", log)
            self.assertFalse(os.path.exists(out), "output was written despite a fatal collision")


class OutputSafetyTest(unittest.TestCase):
    def test_non_empty_output_needs_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            os.makedirs(out)
            write_tree(out, {"keepsake.txt": "not mine to delete\n"})
            code, log = build(repo, out)
            self.assertNotEqual(code, 0)
            self.assertIn("--force", log)
            self.assertEqual(read(os.path.join(out, "keepsake.txt")), "not mine to delete\n")

            code, log = build(repo, out, "--force")
            self.assertEqual(code, 0, log)
            self.assertFalse(os.path.exists(os.path.join(out, "keepsake.txt")))
            self.assertTrue(os.path.exists(os.path.join(out, "headcount-package.json")))

    def test_empty_existing_output_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            os.makedirs(out)
            code, log = build(repo, out)
            self.assertEqual(code, 0, log)


class CheckFlagTest(unittest.TestCase):
    def test_check_passes_on_a_fresh_build_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)

            code, log = build(repo, out, "--check")
            self.assertEqual(code, 0, log)

            with open(os.path.join(out, "skills", "forecasting", "SKILL.md"), "a",
                      encoding="utf-8") as f:
                f.write("\ndrifted\n")
            code, log = build(repo, out, "--check")
            self.assertEqual(code, 1)
            self.assertIn("skills/forecasting/SKILL.md", log)

    def test_check_detects_a_skill_added_to_the_canonical_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(os.path.join(tmp, "repo"), SIMPLE)
            out = os.path.join(tmp, "pkg")
            self.assertEqual(build(repo, out)[0], 0)
            write_tree(repo, {"plugins/security/skills/incident-response/SKILL.md":
                              skill_md("incident-response")})
            code, log = build(repo, out, "--check")
            self.assertEqual(code, 1)
            self.assertIn("skills/incident-response/SKILL.md", log)


class ValidatorTest(unittest.TestCase):
    def package(self, tmp, layout=None, extra=None):
        repo = make_repo(os.path.join(tmp, "repo"), layout or SIMPLE, extra)
        out = os.path.join(tmp, "pkg")
        code, log = build(repo, out)
        self.assertEqual(code, 0, log)
        return repo, out

    def test_fresh_build_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            code, log = validate(pkg, repo)
            self.assertEqual(code, 0, log)
            self.assertIn("codex package: 3 skills, 2 agents, 0 problems", log)

    def test_tampered_file_content_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            with open(os.path.join(pkg, "skills", "forecasting", "SKILL.md"), "a",
                      encoding="utf-8") as f:
                f.write("\ntampered\n")
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("skills/forecasting/SKILL.md", log)

    def test_deleted_file_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            os.remove(os.path.join(pkg, "skills", "threat-modeling", "SKILL.md"))
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("skills/threat-modeling/SKILL.md", log)

    def test_deleted_charter_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            os.remove(os.path.join(pkg, "agents", "security.md"))
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("agents/security.md", log)

    def test_extra_file_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            write_tree(pkg, {"skills/smuggled/SKILL.md": skill_md("smuggled")})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("skills/smuggled/SKILL.md", log)

    def test_wrong_skill_count_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            path = os.path.join(pkg, "headcount-package.json")
            man = json.loads(read(path))
            man["skill_count"] = 99
            write_tree(pkg, {"headcount-package.json":
                             json.dumps(man, indent=2, sort_keys=True) + "\n"})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("skill_count", log)

    def test_wrong_agent_count_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            man = manifest_of(pkg)
            man["agent_count"] = 0
            write_tree(pkg, {"headcount-package.json":
                             json.dumps(man, indent=2, sort_keys=True) + "\n"})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("agent_count", log)

    def test_corrupt_manifest_json_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            write_tree(pkg, {"headcount-package.json": "{not json at all"})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("headcount-package.json", log)

    def test_missing_manifest_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            os.remove(os.path.join(pkg, "headcount-package.json"))
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("headcount-package.json", log)

    def test_wrong_format_field_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            man = manifest_of(pkg)
            man["format"] = "headcount-package/99"
            write_tree(pkg, {"headcount-package.json":
                             json.dumps(man, indent=2, sort_keys=True) + "\n"})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("format", log)

    def test_stale_build_id_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            man = manifest_of(pkg)
            man["build_id"] = "0" * 64
            write_tree(pkg, {"headcount-package.json":
                             json.dumps(man, indent=2, sort_keys=True) + "\n"})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("build_id", log)

    def test_a_skill_added_to_the_canonical_tree_after_the_build_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            write_tree(repo, {"plugins/security/skills/incident-response/SKILL.md":
                              skill_md("incident-response")})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("incident-response", log)

    def test_canonical_collision_is_reported_by_the_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkg = self.package(tmp)
            write_tree(repo, {"plugins/security/skills/forecasting/SKILL.md":
                              skill_md("forecasting")})
            code, log = validate(pkg, repo)
            self.assertEqual(code, 1)
            self.assertIn("forecasting", log)


class RealRepositoryTest(unittest.TestCase):
    """The builder must work on the tree it ships in, not only on fixtures."""

    def test_build_and_validate_the_real_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "codex")
            code, log = run([BUILDER, "--output", out], cwd=REPO)
            self.assertEqual(code, 0, log)
            man = manifest_of(out)
            canonical_skills = sum(
                len([d for d in os.listdir(os.path.join(REPO, "plugins", p, "skills"))
                     if os.path.isdir(os.path.join(REPO, "plugins", p, "skills", d))])
                for p in os.listdir(os.path.join(REPO, "plugins"))
                if os.path.isdir(os.path.join(REPO, "plugins", p, "skills")))
            self.assertEqual(man["skill_count"], canonical_skills)
            self.assertEqual(man["agent_count"],
                             len([f for f in os.listdir(os.path.join(REPO, ".claude", "agents"))
                                  if f.endswith(".md")]))
            code, log = run([VALIDATOR, out], cwd=REPO)
            self.assertEqual(code, 0, log)
            self.assertIn("0 problems", log)
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
