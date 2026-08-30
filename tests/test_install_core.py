"""Safety tests for the runtime-package installer (scripts/install/core.py).

An installer is the one script in this repository that can destroy work that is not its own:
it writes into a directory the user already lives in. So the cases that matter are the ones
where the target is *not* pristine — a hand-edited agent file, an unrelated `.agents/` tree,
a half-finished install — and every one of them is fabricated here in a tempdir. Asserting
that a clean install into an empty directory works proves almost nothing about that.

Each destructive guarantee in the plan has a test whose failure would mean user data was lost.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from install import core  # noqa: E402

PACKAGE_FILES = {
    "AGENTS.md": "# Headcount\n\nRouting preamble.\n",
    "README.md": "# Package readme\n",
    "agents/chief-executive.md": "---\nname: chief-executive\n---\n\nCEO agent.\n",
    "skills/forecasting/SKILL.md": "---\nname: forecasting\n---\n\nForecast things.\n",
    "skills/forecasting/reference.md": "Supporting reference.\n",
}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_tree(root, tree):
    """tree: {relative path: content}. Creates parents."""
    for rel, content in tree.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)


def read_file(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read(root, rel):
    return read_file(os.path.join(root, rel))


def build_package(root, files=None, **overrides):
    """Write a package matching the headcount-package/1 contract, with correct hashes.

    `overrides` replaces manifest fields after they are computed, which is how the tampered
    and malformed-package cases are built.
    """
    files = PACKAGE_FILES if files is None else files
    os.makedirs(root, exist_ok=True)
    write_tree(root, files)
    hashes = {rel: sha256_text(content) for rel, content in files.items()}
    digest = hashlib.sha256()
    for rel in sorted(hashes):
        digest.update(f"{rel}\0{hashes[rel]}\0".encode("utf-8"))
    manifest = {
        "format": "headcount-package/1",
        "runtime": "codex",
        "headcount_version": "1.4.0",
        "source_commit": "a" * 40,
        "build_id": digest.hexdigest(),
        "skill_count": len({r.split("/")[1] for r in files if r.startswith("skills/")}),
        "agent_count": len([r for r in files if r.startswith("agents/")]),
        "files": hashes,
    }
    manifest.update(overrides)
    with open(os.path.join(root, "headcount-package.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return root


def read_only_is_enforced():
    """Root ignores mode bits, so the read-only case cannot be simulated for every runner."""
    probe = tempfile.mkdtemp()
    try:
        os.chmod(probe, 0o500)
        try:
            with open(os.path.join(probe, "probe"), "w", encoding="utf-8"):
                pass
            return False
        except OSError:
            return True
    finally:
        os.chmod(probe, 0o700)
        shutil.rmtree(probe)


class InstallerTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)
        self.package = build_package(os.path.join(self.root, "package"))
        self.target = os.path.join(self.root, "target")

    def _cleanup(self):
        for dirpath, dirnames, _ in os.walk(self.root):
            for name in dirnames:
                os.chmod(os.path.join(dirpath, name), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def files_under(self, root):
        found = set()
        for dirpath, _, names in os.walk(root):
            for name in names:
                found.add(os.path.relpath(os.path.join(dirpath, name), root))
        return found

    def manifest(self, target=None):
        path = os.path.join(target or self.target, core.INSTALL_MANIFEST)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class FreshInstallTest(InstallerTestCase):
    def test_installs_every_package_file(self):
        result = core.apply_install(package_dir=self.package, target_dir=self.target)
        for rel, content in PACKAGE_FILES.items():
            self.assertEqual(read(self.target, rel), content)
        self.assertEqual(sorted(result.written), sorted(PACKAGE_FILES))
        self.assertEqual(result.removed, [])
        self.assertIsNone(result.backup_dir)

    def test_manifest_records_hashes_matching_disk(self):
        core.apply_install(package_dir=self.package, target_dir=self.target)
        manifest = self.manifest()
        self.assertEqual(manifest["format"], "headcount-install/1")
        self.assertEqual(manifest["headcount_version"], "1.4.0")
        self.assertEqual(manifest["runtime"], "codex")
        self.assertEqual(manifest["source_commit"], "a" * 40)
        self.assertEqual(sorted(manifest["files"]), sorted(PACKAGE_FILES))
        for rel, recorded in manifest["files"].items():
            self.assertEqual(recorded, sha256_text(read(self.target, rel)))

    def test_plan_reports_adds_and_touches_nothing(self):
        plan = core.plan_install(self.package, self.target)
        self.assertEqual(sorted(plan.adds), sorted(PACKAGE_FILES))
        self.assertEqual(plan.replacements, [])
        self.assertEqual(plan.collisions, [])
        self.assertEqual(plan.unmanaged, [])
        self.assertFalse(plan.backup_required)
        self.assertEqual(plan.headcount_version, "1.4.0")
        self.assertFalse(os.path.exists(self.target))

    def test_dry_run_writes_nothing(self):
        result = core.apply_install(package_dir=self.package, target_dir=self.target,
                                    dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertEqual(sorted(result.written), sorted(PACKAGE_FILES))
        self.assertFalse(os.path.exists(self.target))

    def test_dry_run_plan_matches_real_plan(self):
        dry = core.apply_install(package_dir=self.package, target_dir=self.target, dry_run=True)
        wet = core.apply_install(package_dir=self.package, target_dir=self.target)
        self.assertEqual(dry.plan.adds, wet.plan.adds)
        self.assertEqual(dry.plan.collisions, wet.plan.collisions)
        self.assertEqual(dry.written, wet.written)

    def test_reinstall_of_same_package_is_replacement_not_collision(self):
        core.apply_install(package_dir=self.package, target_dir=self.target)
        plan = core.plan_install(self.package, self.target)
        self.assertEqual(plan.adds, [])
        self.assertEqual(sorted(plan.replacements), sorted(PACKAGE_FILES))
        self.assertEqual(plan.collisions, [])

    def test_target_path_with_spaces(self):
        target = os.path.join(self.root, "my codex home", "agent files")
        core.apply_install(package_dir=self.package, target_dir=target)
        self.assertEqual(read(target, "AGENTS.md"), PACKAGE_FILES["AGENTS.md"])
        self.assertTrue(os.path.exists(os.path.join(target, core.INSTALL_MANIFEST)))

    def test_staging_area_is_cleaned_up(self):
        core.apply_install(package_dir=self.package, target_dir=self.target)
        leftovers = [n for n in os.listdir(self.target) if n.startswith(".headcount-staging")]
        self.assertEqual(leftovers, [])


class CollisionTest(InstallerTestCase):
    def setUp(self):
        super().setUp()
        write_tree(self.target, {
            "AGENTS.md": "MY OWN CONTENT, NOT HEADCOUNT'S\n",
            "notes.md": "personal notes\n",
            "agents/mine.md": "an agent I wrote\n",
        })

    def test_install_aborts_on_unmanaged_collision_and_deletes_nothing(self):
        before = self.files_under(self.target)
        with self.assertRaises(core.CollisionError):
            core.apply_install(package_dir=self.package, target_dir=self.target)
        self.assertEqual(self.files_under(self.target), before)
        self.assertEqual(read(self.target, "AGENTS.md"), "MY OWN CONTENT, NOT HEADCOUNT'S\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, core.INSTALL_MANIFEST)))

    def test_plan_names_the_colliding_path_and_requires_a_backup(self):
        plan = core.plan_install(self.package, self.target)
        self.assertEqual([c.path for c in plan.collisions], ["AGENTS.md"])
        self.assertEqual(plan.collisions[0].reason, core.UNMANAGED_EXISTS)
        self.assertIn("notes.md", plan.unmanaged)
        self.assertIn("agents/mine.md", plan.unmanaged)
        self.assertTrue(plan.backup_required)

    def test_force_backs_up_the_collided_file_before_overwriting(self):
        result = core.apply_install(package_dir=self.package, target_dir=self.target, force=True)
        self.assertEqual(read(self.target, "AGENTS.md"), PACKAGE_FILES["AGENTS.md"])
        self.assertIsNotNone(result.backup_dir)
        backup = os.path.join(result.backup_dir, "AGENTS.md")
        self.assertEqual(read_file(backup), "MY OWN CONTENT, NOT HEADCOUNT'S\n")

    def test_backup_directory_name_carries_a_utc_timestamp(self):
        result = core.apply_install(package_dir=self.package, target_dir=self.target, force=True)
        stamp = os.path.basename(result.backup_dir)
        self.assertRegex(stamp, r"^\d{8}T\d{6}Z")

    def test_force_never_deletes_unmanaged_files(self):
        core.apply_install(package_dir=self.package, target_dir=self.target, force=True)
        self.assertEqual(read(self.target, "notes.md"), "personal notes\n")
        self.assertEqual(read(self.target, "agents/mine.md"), "an agent I wrote\n")
        self.assertNotIn("notes.md", self.manifest()["files"])

    def test_force_with_backup_disabled_overwrites_without_a_copy(self):
        result = core.apply_install(package_dir=self.package, target_dir=self.target,
                                    force=True, backup=False)
        self.assertIsNone(result.backup_dir)
        self.assertFalse(os.path.exists(os.path.join(self.target, core.BACKUP_DIR)))

    def test_force_dry_run_still_writes_nothing(self):
        before = self.files_under(self.target)
        core.apply_install(package_dir=self.package, target_dir=self.target,
                           force=True, dry_run=True)
        self.assertEqual(self.files_under(self.target), before)
        self.assertEqual(read(self.target, "AGENTS.md"), "MY OWN CONTENT, NOT HEADCOUNT'S\n")


class UpdateTest(InstallerTestCase):
    def setUp(self):
        super().setUp()
        core.apply_install(package_dir=self.package, target_dir=self.target)
        write_tree(self.target, {"notes.md": "personal notes\n"})
        next_files = dict(PACKAGE_FILES)
        next_files["AGENTS.md"] = "# Headcount\n\nRewritten preamble.\n"
        del next_files["skills/forecasting/reference.md"]
        self.next_package = build_package(os.path.join(self.root, "package2"), next_files,
                                          headcount_version="1.5.0")
        self.next_files = next_files

    def test_overwrites_unmodified_managed_files(self):
        core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertEqual(read(self.target, "AGENTS.md"), "# Headcount\n\nRewritten preamble.\n")
        self.assertEqual(self.manifest()["headcount_version"], "1.5.0")

    def test_preserves_unmanaged_files(self):
        core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertEqual(read(self.target, "notes.md"), "personal notes\n")

    def test_removes_managed_files_the_new_package_dropped(self):
        result = core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertIn("skills/forecasting/reference.md", result.removed)
        self.assertFalse(os.path.exists(
            os.path.join(self.target, "skills/forecasting/reference.md")))
        self.assertNotIn("skills/forecasting/reference.md", self.manifest()["files"])

    def test_flags_and_skips_a_locally_modified_managed_file(self):
        write_tree(self.target, {"AGENTS.md": "I edited this by hand\n"})
        result = core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertIn("AGENTS.md", result.skipped)
        self.assertEqual(read(self.target, "AGENTS.md"), "I edited this by hand\n")
        self.assertEqual([c.reason for c in result.plan.collisions if c.path == "AGENTS.md"],
                         [core.LOCALLY_MODIFIED])

    def test_skipped_file_keeps_its_original_recorded_hash(self):
        original = self.manifest()["files"]["AGENTS.md"]
        write_tree(self.target, {"AGENTS.md": "I edited this by hand\n"})
        core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertEqual(self.manifest()["files"]["AGENTS.md"], original)

    def test_forced_update_backs_up_the_modified_file_then_overwrites(self):
        write_tree(self.target, {"AGENTS.md": "I edited this by hand\n"})
        result = core.update_install(package_dir=self.next_package, target_dir=self.target,
                                     force=True)
        self.assertEqual(read(self.target, "AGENTS.md"), "# Headcount\n\nRewritten preamble.\n")
        self.assertEqual(read_file(os.path.join(result.backup_dir, "AGENTS.md")),
                         "I edited this by hand\n")

    def test_keeps_a_modified_file_the_new_package_dropped(self):
        write_tree(self.target, {"skills/forecasting/reference.md": "my own notes here\n"})
        result = core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertIn("skills/forecasting/reference.md", result.skipped)
        self.assertEqual(read(self.target, "skills/forecasting/reference.md"),
                         "my own notes here\n")
        self.assertIn("skills/forecasting/reference.md", self.manifest()["files"])

    def test_forced_update_removes_a_modified_dropped_file_after_backing_it_up(self):
        write_tree(self.target, {"skills/forecasting/reference.md": "my own notes here\n"})
        result = core.update_install(package_dir=self.next_package, target_dir=self.target,
                                     force=True)
        self.assertFalse(os.path.exists(
            os.path.join(self.target, "skills/forecasting/reference.md")))
        self.assertEqual(read_file(os.path.join(result.backup_dir,
                                                 "skills/forecasting/reference.md")),
                         "my own notes here\n")

    def test_unmanaged_file_in_the_way_aborts_without_force(self):
        os.remove(os.path.join(self.target, "AGENTS.md"))
        manifest = self.manifest()
        del manifest["files"]["AGENTS.md"]
        with open(os.path.join(self.target, core.INSTALL_MANIFEST), "w",
                  encoding="utf-8") as handle:
            json.dump(manifest, handle)
        write_tree(self.target, {"AGENTS.md": "someone else put this here\n"})
        with self.assertRaises(core.CollisionError):
            core.update_install(package_dir=self.next_package, target_dir=self.target)
        self.assertEqual(read(self.target, "AGENTS.md"), "someone else put this here\n")

    def test_dry_run_changes_nothing(self):
        before = {rel: read(self.target, rel) for rel in self.files_under(self.target)}
        core.update_install(package_dir=self.next_package, target_dir=self.target, dry_run=True)
        after = {rel: read(self.target, rel) for rel in self.files_under(self.target)}
        self.assertEqual(before, after)

    def test_update_without_an_existing_install_is_refused(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        with self.assertRaises(core.InstallError):
            core.update_install(package_dir=self.next_package, target_dir=empty)


class UninstallTest(InstallerTestCase):
    def setUp(self):
        super().setUp()
        core.apply_install(package_dir=self.package, target_dir=self.target)
        write_tree(self.target, {
            "notes.md": "personal notes\n",
            "skills/mine/SKILL.md": "my own skill\n",
        })

    def test_removes_only_managed_files(self):
        result = core.uninstall(self.target)
        self.assertEqual(sorted(result.removed), sorted(PACKAGE_FILES))
        self.assertEqual(read(self.target, "notes.md"), "personal notes\n")
        self.assertEqual(read(self.target, "skills/mine/SKILL.md"), "my own skill\n")
        for rel in PACKAGE_FILES:
            self.assertFalse(os.path.exists(os.path.join(self.target, rel)), rel)

    def test_removes_the_manifest_and_prunes_empty_directories(self):
        core.uninstall(self.target)
        self.assertFalse(os.path.exists(os.path.join(self.target, core.INSTALL_MANIFEST)))
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "skills", "forecasting")))
        self.assertTrue(os.path.isdir(os.path.join(self.target, "skills", "mine")))

    def test_skips_a_locally_modified_managed_file(self):
        write_tree(self.target, {"AGENTS.md": "I edited this\n"})
        result = core.uninstall(self.target)
        self.assertIn("AGENTS.md", result.skipped)
        self.assertEqual(read(self.target, "AGENTS.md"), "I edited this\n")
        self.assertEqual(list(self.manifest()["files"]), ["AGENTS.md"])

    def test_force_backs_up_then_removes_a_modified_file(self):
        write_tree(self.target, {"AGENTS.md": "I edited this\n"})
        result = core.uninstall(self.target, force=True)
        self.assertFalse(os.path.exists(os.path.join(self.target, "AGENTS.md")))
        self.assertEqual(read_file(os.path.join(result.backup_dir, "AGENTS.md")),
                         "I edited this\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, core.INSTALL_MANIFEST)))

    def test_dry_run_removes_nothing(self):
        before = self.files_under(self.target)
        result = core.uninstall(self.target, dry_run=True)
        self.assertEqual(sorted(result.removed), sorted(PACKAGE_FILES))
        self.assertEqual(self.files_under(self.target), before)

    def test_uninstall_without_an_install_is_refused(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        with self.assertRaises(core.InstallError):
            core.uninstall(empty)


class PackageVerificationTest(InstallerTestCase):
    def test_tampered_file_is_refused(self):
        write_tree(self.package, {"AGENTS.md": "someone changed this after the build\n"})
        with self.assertRaises(core.PackageError) as caught:
            core.plan_install(self.package, self.target)
        self.assertIn("AGENTS.md", str(caught.exception))
        self.assertFalse(os.path.exists(self.target))

    def test_missing_file_is_refused(self):
        os.remove(os.path.join(self.package, "README.md"))
        with self.assertRaises(core.PackageError) as caught:
            core.plan_install(self.package, self.target)
        self.assertIn("README.md", str(caught.exception))

    def test_unlisted_extra_file_is_refused(self):
        write_tree(self.package, {"skills/forecasting/extra.md": "not in the manifest\n"})
        with self.assertRaises(core.PackageError):
            core.plan_install(self.package, self.target)

    def test_unknown_format_is_refused(self):
        build_package(self.package, format="headcount-package/2")
        with self.assertRaises(core.PackageError):
            core.plan_install(self.package, self.target)

    def test_missing_manifest_is_refused(self):
        os.remove(os.path.join(self.package, core.PACKAGE_MANIFEST))
        with self.assertRaises(core.PackageError):
            core.plan_install(self.package, self.target)

    def test_unparsable_manifest_is_refused(self):
        with open(os.path.join(self.package, core.PACKAGE_MANIFEST), "w",
                  encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(core.PackageError):
            core.plan_install(self.package, self.target)

    def test_escaping_path_is_refused(self):
        files = dict(PACKAGE_FILES)
        package = build_package(os.path.join(self.root, "evil"), files)
        manifest_path = os.path.join(package, core.PACKAGE_MANIFEST)
        manifest = json.loads(read_file(manifest_path))
        manifest["files"]["../escaped.md"] = manifest["files"].pop("README.md")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        with self.assertRaises(core.PackageError) as caught:
            core.plan_install(package, self.target)
        self.assertIn("escaped", str(caught.exception))

    def test_symlink_in_package_is_refused(self):
        os.symlink("/etc/passwd", os.path.join(self.package, "link.md"))
        with self.assertRaises(core.PackageError):
            core.plan_install(self.package, self.target)


class FailureTest(InstallerTestCase):
    @unittest.skipUnless(read_only_is_enforced(), "mode bits do not restrict this user")
    def test_read_only_target_fails_without_a_partial_manifest(self):
        os.makedirs(self.target)
        os.chmod(self.target, 0o500)
        with self.assertRaises(core.InstallError):
            core.apply_install(package_dir=self.package, target_dir=self.target)
        os.chmod(self.target, 0o700)
        self.assertEqual(self.files_under(self.target), set())

    def test_interruption_leaves_no_manifest_and_no_truncated_file(self):
        placed = []
        real_place = core._place

        def fail_on_second(staged, destination):
            if len(placed) >= 2:
                raise OSError("simulated interruption")
            placed.append(destination)
            return real_place(staged, destination)

        with mock.patch.object(core, "_place", fail_on_second):
            with self.assertRaises(core.InstallError):
                core.apply_install(package_dir=self.package, target_dir=self.target)
        self.assertFalse(os.path.exists(os.path.join(self.target, core.INSTALL_MANIFEST)))
        for path in placed:
            rel = os.path.relpath(path, self.target)
            self.assertEqual(read(self.target, rel), PACKAGE_FILES[rel])
        leftovers = [n for n in os.listdir(self.target) if n.startswith(".headcount-staging")]
        self.assertEqual(leftovers, [])

    def test_target_that_is_a_file_is_refused(self):
        with open(self.target, "w", encoding="utf-8") as handle:
            handle.write("not a directory\n")
        with self.assertRaises(core.InstallError):
            core.apply_install(package_dir=self.package, target_dir=self.target)

    def test_corrupt_install_manifest_is_refused(self):
        os.makedirs(self.target)
        with open(os.path.join(self.target, core.INSTALL_MANIFEST), "w",
                  encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(core.InstallError):
            core.plan_install(self.package, self.target)


if __name__ == "__main__":
    unittest.main()
