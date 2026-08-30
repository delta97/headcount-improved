"""Documentation-drift guards that run against the real tree, not fixtures.

CONTRIBUTING.md once said "Four checks" while check-all.sh ran nine; nothing failed. These
tests pin the statements most likely to rot to the artifacts they describe, so the fix for a
new check or generator is a one-line doc edit demanded by CI rather than a reader's
confusion months later.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


class DocsMatchToolingTest(unittest.TestCase):
    def test_every_check_all_check_is_documented_in_contributing(self):
        """Each `run "Title"` line in check-all.sh must appear in CONTRIBUTING.md's check
        table, so the documented list and the executed list cannot diverge again."""
        script = read("scripts/check-all.sh")
        titles = re.findall(r'^run "([^"]+)"', script, re.M)
        self.assertGreater(len(titles), 5, "check-all.sh should declare its checks via run \"...\"")
        contributing = read("CONTRIBUTING.md")
        for title in titles:
            self.assertIn(title, contributing,
                          f"check-all.sh runs {title!r} but CONTRIBUTING.md does not list it — "
                          "update the check table in CONTRIBUTING.md")

    def test_contributing_does_not_hardcode_a_wrong_check_count(self):
        script = read("scripts/check-all.sh")
        n = len(re.findall(r'^run "', script, re.M))
        contributing = read("CONTRIBUTING.md")
        words = {4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine",
                 10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen"}
        for count, word in words.items():
            if count != n:
                self.assertNotIn(f"{word} checks", contributing,
                                 f"CONTRIBUTING.md claims '{word} checks' but check-all.sh runs {n}")

    def test_generated_files_carry_their_do_not_edit_notice(self):
        self.assertIn("edit that, not this file", read("README.md"))
        self.assertIn("BEGIN GENERATED", read("docs/org-chart.md"))

    def test_scripts_referenced_by_docs_exist(self):
        for doc in ("CONTRIBUTING.md", "README.md", "evals/README.md"):
            for rel in re.findall(r"scripts/[a-z0-9-]+\.(?:py|sh)", read(doc)):
                self.assertTrue(os.path.exists(os.path.join(REPO, rel)),
                                f"{doc} references {rel}, which does not exist")

    def test_readme_documents_the_namespace_model_the_validator_enforces(self):
        """D32: the README's collision claim and the validator's uniqueness rule must
        describe the same model — per-department uniqueness under department:skill."""
        self.assertIn("department:skill", read("README.md"))
        validator = read("scripts/validate-skills.py")
        self.assertIn("(department, skill)", validator)


if __name__ == "__main__":
    unittest.main()
