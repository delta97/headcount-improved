"""Edge-case tests for scripts/validate-skills.py, run against throwaway fixture trees.

The validator was previously exercised only by the real tree, which is entirely valid — so
the failure paths (the ones the check exists for) were the untested ones.
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "validate-skills.py")

GOOD_DESC = ("Does one clearly stated thing for one clearly stated situation, described at "
             "enough length that routing can actually discriminate between neighbors.")


def run_validator(tree):
    """tree: {relative path: content}. Returns (exit_code, output)."""
    with tempfile.TemporaryDirectory() as root:
        for rel, content in tree.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        proc = subprocess.run([sys.executable, SCRIPT], cwd=root,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


def skill(name, description=GOOD_DESC, frontmatter=None):
    if frontmatter is None:
        frontmatter = f"name: {name}\ndescription: {description}"
    return f"---\n{frontmatter}\n---\n\n# {name}\n"


class ValidateSkillsTest(unittest.TestCase):
    def test_valid_tree_passes(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill("one-skill"),
            "plugins/beta/skills/other-skill/SKILL.md": skill("other-skill"),
        })
        self.assertEqual(code, 0, out)
        self.assertIn("2 skills checked, 0 problems", out)

    def test_same_name_in_two_departments_is_a_note_not_a_failure(self):
        code, out = run_validator({
            "plugins/alpha/skills/forecasting/SKILL.md": skill("forecasting"),
            "plugins/beta/skills/forecasting/SKILL.md": skill("forecasting"),
        })
        self.assertEqual(code, 0, out)
        self.assertIn("note:", out)
        self.assertIn("more than one department", out)

    def test_name_directory_mismatch_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill("wrong-name"),
        })
        self.assertEqual(code, 1)
        self.assertIn("!= directory", out)

    def test_uppercase_name_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/BadName/SKILL.md": skill("BadName"),
        })
        self.assertEqual(code, 1)
        self.assertIn("not lowercase-hyphenated", out)

    def test_thin_description_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill("one-skill", description="Too short."),
        })
        self.assertEqual(code, 1)
        self.assertIn("too thin", out)

    def test_missing_frontmatter_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": "# no frontmatter here\n",
        })
        self.assertEqual(code, 1)
        self.assertIn("no frontmatter", out)

    def test_unknown_key_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill(
                "one-skill", frontmatter=f"name: one-skill\ndescription: {GOOD_DESC}\nversion: 2"),
        })
        self.assertEqual(code, 1)
        self.assertIn("unsupported frontmatter key 'version'", out)

    def test_folded_scalar_fails_with_reason(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill(
                "one-skill", frontmatter="name: one-skill\ndescription: >\n  folded text"),
        })
        self.assertEqual(code, 1)
        self.assertIn("multi-line/folded", out)

    def test_indented_continuation_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill(
                "one-skill",
                frontmatter=f"name: one-skill\ndescription: {GOOD_DESC}\n  continued here"),
        })
        self.assertEqual(code, 1)
        self.assertIn("indented continuation", out)

    def test_duplicate_key_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill(
                "one-skill", frontmatter=f"name: one-skill\nname: one-skill\ndescription: {GOOD_DESC}"),
        })
        self.assertEqual(code, 1)
        self.assertIn("duplicate frontmatter key", out)

    def test_missing_description_fails(self):
        code, out = run_validator({
            "plugins/alpha/skills/one-skill/SKILL.md": skill("one-skill", frontmatter="name: one-skill"),
        })
        self.assertEqual(code, 1)
        self.assertIn("missing description", out)


if __name__ == "__main__":
    unittest.main()
