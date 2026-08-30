"""Exit-code and output contract for the installer CLI, plus the GUI's graceful refusal.

The CLI is what a script or a CI job calls, so its exit codes are the interface: 0 applied,
1 refused, 2 called wrongly. A refusal that exits 0 would let an automated install report
success while the target was left untouched, which is the failure this file exists to prevent.

The GUI is checked only for the two properties that can be verified without a display: it
imports without tkinter present, and it says where to go instead of failing with a traceback.
"""
import json
import os
import subprocess
import sys
import unittest

from tests.test_install_core import (PACKAGE_FILES, InstallerTestCase, build_package, read,
                                     read_file, write_tree)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "scripts", "install", "cli.py")
GUI = os.path.join(REPO, "platforms", "codex", "installer_gui.py")


def _labels(text):
    """The first token of every line: the shape of the output, independent of the values."""
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def run(*args, env=None):
    proc = subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


class CliInstallTest(InstallerTestCase):
    def test_plan_reports_counts_without_writing(self):
        code, out = run("plan", "--package", self.package, "--target", self.target)
        self.assertEqual(code, 0, out)
        self.assertIn("add", out)
        self.assertIn("1.4.0", out)
        self.assertFalse(os.path.exists(self.target))

    def test_dry_run_matches_the_shape_of_a_real_run(self):
        dry_code, dry_out = run("install", "--package", self.package, "--target", self.target,
                                "--dry-run")
        self.assertEqual(dry_code, 0, dry_out)
        self.assertFalse(os.path.exists(self.target))
        code, out = run("install", "--package", self.package, "--target", self.target)
        self.assertEqual(code, 0, out)
        self.assertEqual(_labels(dry_out), _labels(out))
        self.assertIn("dry run", dry_out)

    def test_install_writes_the_manifest(self):
        code, out = run("install", "--package", self.package, "--target", self.target)
        self.assertEqual(code, 0, out)
        manifest = json.loads(read_file(os.path.join(self.target,
                                                     ".headcount-install.json")))
        self.assertEqual(sorted(manifest["files"]), sorted(PACKAGE_FILES))

    def test_collision_exits_one_and_changes_nothing(self):
        write_tree(self.target, {"AGENTS.md": "mine\n"})
        code, out = run("install", "--package", self.package, "--target", self.target)
        self.assertEqual(code, 1, out)
        self.assertIn("AGENTS.md", out)
        self.assertEqual(read(self.target, "AGENTS.md"), "mine\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, "README.md")))

    def test_force_resolves_the_collision(self):
        write_tree(self.target, {"AGENTS.md": "mine\n"})
        code, out = run("install", "--package", self.package, "--target", self.target, "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(read(self.target, "AGENTS.md"), PACKAGE_FILES["AGENTS.md"])

    def test_tampered_package_exits_one(self):
        write_tree(self.package, {"AGENTS.md": "tampered after build\n"})
        code, out = run("install", "--package", self.package, "--target", self.target)
        self.assertEqual(code, 1, out)
        self.assertIn("AGENTS.md", out)
        self.assertFalse(os.path.exists(self.target))


class CliUpdateUninstallTest(InstallerTestCase):
    def setUp(self):
        super().setUp()
        run("install", "--package", self.package, "--target", self.target)
        next_files = dict(PACKAGE_FILES)
        next_files["AGENTS.md"] = "# Headcount\n\nRewritten.\n"
        self.next_package = build_package(os.path.join(self.root, "package2"), next_files,
                                          headcount_version="1.5.0")

    def test_update_exits_zero_and_reports_the_new_version(self):
        code, out = run("update", "--package", self.next_package, "--target", self.target)
        self.assertEqual(code, 0, out)
        self.assertIn("1.5.0", out)
        self.assertEqual(read(self.target, "AGENTS.md"), "# Headcount\n\nRewritten.\n")

    def test_update_that_skips_a_modified_file_exits_one(self):
        write_tree(self.target, {"AGENTS.md": "hand edited\n"})
        code, out = run("update", "--package", self.next_package, "--target", self.target)
        self.assertEqual(code, 1, out)
        self.assertIn("AGENTS.md", out)
        self.assertEqual(read(self.target, "AGENTS.md"), "hand edited\n")

    def test_uninstall_leaves_user_files(self):
        write_tree(self.target, {"notes.md": "mine\n"})
        code, out = run("uninstall", "--target", self.target)
        self.assertEqual(code, 0, out)
        self.assertEqual(read(self.target, "notes.md"), "mine\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, "AGENTS.md")))

    def test_uninstall_dry_run_removes_nothing(self):
        code, out = run("uninstall", "--target", self.target, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(os.path.join(self.target, "AGENTS.md")))

    def test_uninstall_without_an_install_exits_one(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        code, out = run("uninstall", "--target", empty)
        self.assertEqual(code, 1, out)


class CliUsageTest(InstallerTestCase):
    def test_missing_required_argument_exits_two(self):
        code, _ = run("install", "--target", self.target)
        self.assertEqual(code, 2)

    def test_unknown_subcommand_exits_two(self):
        code, _ = run("frobnicate")
        self.assertEqual(code, 2)

    def test_no_subcommand_exits_two(self):
        code, _ = run()
        self.assertEqual(code, 2)

    def test_missing_package_directory_exits_two(self):
        code, out = run("install", "--package", os.path.join(self.root, "nope"),
                        "--target", self.target)
        self.assertEqual(code, 2, out)


class GuiTest(unittest.TestCase):
    def test_module_imports_without_tkinter(self):
        script = ("import sys, importlib.util;"
                  f"spec = importlib.util.spec_from_file_location('gui', {GUI!r});"
                  "module = importlib.util.module_from_spec(spec);"
                  "spec.loader.exec_module(module);"
                  "assert 'tkinter' not in sys.modules, 'tkinter imported at module level';"
                  "assert hasattr(module, 'main')")
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_without_a_display_it_points_at_the_cli(self):
        env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
        proc = subprocess.run([sys.executable, GUI], capture_output=True, text=True, env=env)
        self.assertNotEqual(proc.returncode, 0)
        output = proc.stdout + proc.stderr
        self.assertIn("scripts/install/cli.py", output)
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
