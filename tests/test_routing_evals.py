"""Edge-case tests for scripts/validate-routing-evals.py against throwaway fixture trees."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "validate-routing-evals.py")

SKILLS = ["plugins/alpha/skills/one-skill/SKILL.md",
          "plugins/alpha/skills/two-skill/SKILL.md",
          "plugins/beta/skills/blue-skill/SKILL.md"]


def case(cid="case-001", **over):
    c = {"id": cid, "prompt": "A realistic request that is long enough.",
         "expected": ["alpha:one-skill"], "acceptable": [], "forbidden": [],
         "tags": ["positive"]}
    c.update(over)
    return c


def run_validator(cases, uncovered="alpha:two-skill\nbeta:blue-skill\n", skills=SKILLS):
    with tempfile.TemporaryDirectory() as root:
        for rel in skills:
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("---\nname: x\ndescription: y\n---\n")
        os.makedirs(os.path.join(root, "evals", "routing"), exist_ok=True)
        with open(os.path.join(root, "evals", "routing", "cases.jsonl"), "w",
                  encoding="utf-8") as f:
            for c in cases:
                f.write((c if isinstance(c, str) else json.dumps(c)) + "\n")
        if uncovered is not None:
            with open(os.path.join(root, "evals", "routing", "uncovered.txt"), "w",
                      encoding="utf-8") as f:
                f.write("# comment line\n" + uncovered)
        proc = subprocess.run([sys.executable, SCRIPT], cwd=root, capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


class RoutingEvalValidationTest(unittest.TestCase):
    def test_sound_fixtures_pass(self):
        code, out = run_validator([case()])
        self.assertEqual(code, 0, out)
        self.assertIn("1/3 skills covered", out)

    def test_unknown_skill_reference_fails(self):
        code, out = run_validator([case(expected=["alpha:no-such-skill"])])
        self.assertEqual(code, 1)
        self.assertIn("not an installed skill", out)

    def test_malformed_reference_fails(self):
        code, out = run_validator([case(forbidden=["not-namespaced"])])
        self.assertEqual(code, 1)
        self.assertIn("not department:skill", out)

    def test_duplicate_id_fails(self):
        code, out = run_validator([case(), case(expected=["alpha:two-skill"])])
        self.assertEqual(code, 1)
        self.assertIn("duplicate case id", out)

    def test_expected_and_forbidden_overlap_fails(self):
        code, out = run_validator([case(forbidden=["alpha:one-skill"])])
        self.assertEqual(code, 1)
        self.assertIn("in both expected and forbidden", out)

    def test_case_asserting_nothing_fails(self):
        code, out = run_validator([case(expected=[], acceptable=[], forbidden=[])])
        self.assertEqual(code, 1)
        self.assertIn("asserts nothing", out)

    def test_missing_field_fails(self):
        c = case()
        del c["tags"]
        code, out = run_validator([c])
        self.assertEqual(code, 1)
        self.assertIn("missing field(s): tags", out)

    def test_invalid_json_line_fails(self):
        code, out = run_validator(['{"id": "broken"'])
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out)

    def test_uncovered_skill_without_exemption_fails(self):
        code, out = run_validator([case()], uncovered="alpha:two-skill\n")
        self.assertEqual(code, 1)
        self.assertIn("beta:blue-skill has no positive routing case", out)

    def test_covered_skill_still_exempted_fails(self):
        code, out = run_validator(
            [case()], uncovered="alpha:one-skill\nalpha:two-skill\nbeta:blue-skill\n")
        self.assertEqual(code, 1)
        self.assertIn("still listed", out)

    def test_stale_exemption_for_removed_skill_fails(self):
        code, out = run_validator(
            [case()], uncovered="alpha:two-skill\nbeta:blue-skill\nbeta:gone-skill\n")
        self.assertEqual(code, 1)
        self.assertIn("remove the stale line", out)

    def test_acceptable_counts_as_coverage(self):
        code, out = run_validator(
            [case(expected=[], acceptable=["alpha:one-skill", "alpha:two-skill"])],
            uncovered="beta:blue-skill\n")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
