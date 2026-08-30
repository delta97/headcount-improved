"""The install engine: plan first, then apply exactly what was planned.

A runtime package is installed into a directory the user already lives in — `~/.codex` holds
their own agent files, their own notes, and possibly an install from an older version. So the
engine is built around one rule: Headcount may only ever delete or overwrite bytes it wrote
itself, and it knows which those are because it recorded them.

`.headcount-install.json` in the target is that record, and the sole authority. A file listed
there whose hash still matches is Headcount's to replace. Anything else — a path that exists
but was never recorded, or a recorded path the user has since edited — is a collision, and a
collision stops the operation rather than resolving it. `force=True` resolves collisions, and
only that path copies the current bytes into a timestamped backup first.

Failure modes this shape is chosen for:

  - An interrupted install leaving a truncated file. Files are copied into a staging directory
    inside the target, hashed there, and moved into place with os.replace, which is atomic on
    the same filesystem. An interruption leaves whole files, never partial ones.
  - A manifest that describes an install that did not happen. It is written last, so a crash
    leaves untracked files (visible as collisions next time) rather than phantom entries.
  - A stale plan. apply recomputes from disk instead of trusting the plan handed to it; the
    plan object carries the operation and the directories, not permission to act on old facts.
  - Adopting the user's edit as ours. A skipped locally modified file keeps its *original*
    recorded hash, so it stays flagged on every future run until someone resolves it.

Nothing here prints. The CLI and the GUI decide how a plan is shown and what is confirmed.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field

PACKAGE_MANIFEST = "headcount-package.json"
PACKAGE_FORMAT = "headcount-package/1"
INSTALL_MANIFEST = ".headcount-install.json"
INSTALL_FORMAT = "headcount-install/1"
BACKUP_DIR = ".headcount-backups"
STAGING_PREFIX = ".headcount-staging-"

INSTALL = "install"
UPDATE = "update"
UNINSTALL = "uninstall"

# Why a path cannot simply be written.
UNMANAGED_EXISTS = "unmanaged-exists"   # present in the target, never recorded as ours
LOCALLY_MODIFIED = "locally-modified"   # recorded as ours, but the bytes have since changed

REQUIRED_PACKAGE_FIELDS = ("runtime", "headcount_version", "source_commit", "build_id", "files")


class InstallError(Exception):
    """Any refusal to act. Callers turn this into an exit code; nothing has been changed."""


class PackageError(InstallError):
    """The package is not one we will install from: malformed, incomplete, or altered."""


class CollisionError(InstallError):
    """The target holds content Headcount did not write, and force was not given."""


@dataclass(frozen=True)
class Collision:
    path: str
    reason: str
    # Blocking collisions stop the operation. A locally modified file blocks an install (the
    # user asked for a clean placement) but not an update or an uninstall, where skipping it
    # and reporting it is the answer that loses no work.
    blocking: bool


@dataclass
class InstallPlan:
    """What an operation would do. Producing one touches nothing."""
    operation: str
    target_dir: str
    package_dir: str = None
    adds: list = field(default_factory=list)
    replacements: list = field(default_factory=list)
    removals: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    unmanaged: list = field(default_factory=list)
    backup_required: bool = False
    headcount_version: str = None
    runtime: str = None
    build_id: str = None
    source_commit: str = None
    package_files: dict = field(default_factory=dict)

    @property
    def blocking(self):
        return [c for c in self.collisions if c.blocking]


@dataclass
class InstallResult:
    plan: InstallPlan
    dry_run: bool
    written: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    backup_dir: str = None

    @property
    def complete(self):
        """False when the target does not fully match the package: something was left alone."""
        return not self.skipped


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_relpath(rel):
    """Manifest paths are data from a file on disk, so they are treated as hostile input."""
    if not rel or rel != rel.strip():
        raise PackageError(f"{rel!r}: empty or padded path in the package manifest")
    if os.path.isabs(rel) or rel.startswith("/") or "\\" in rel or ":" in rel:
        raise PackageError(f"{rel!r}: package paths must be relative and slash-separated")
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PackageError(f"{rel!r}: package path escapes or contains an empty segment")
    if rel == PACKAGE_MANIFEST:
        raise PackageError(f"{rel!r}: the package manifest cannot list itself")


def _walk_files(root, skip_names=()):
    """Relative paths of every regular file under root, and every symlink found on the way.

    Symlinks are reported rather than followed: a link cannot be hash-verified meaningfully,
    and one pointing outside the tree would make an install write wherever it aimed.
    """
    files, links = [], []
    if not os.path.isdir(root):
        return files, links
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in skip_names and not d.startswith(STAGING_PREFIX)]
        for name in list(dirnames):
            if os.path.islink(os.path.join(dirpath, name)):
                links.append(os.path.relpath(os.path.join(dirpath, name), root))
                dirnames.remove(name)
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            if os.path.islink(full):
                links.append(rel)
            else:
                files.append(rel.replace(os.sep, "/"))
    return sorted(files), sorted(links)


def verify_package(package_dir):
    """Return the package manifest, or raise PackageError.

    Every declared file is rehashed. This is the check that makes a package safe to install
    from a download: a build that lost a file, or one whose contents were edited after the
    build, is refused before anything in the target is looked at.
    """
    manifest_path = os.path.join(package_dir, PACKAGE_MANIFEST)
    if not os.path.isdir(package_dir):
        raise PackageError(f"{package_dir}: no such package directory")
    if not os.path.isfile(manifest_path):
        raise PackageError(f"{package_dir}: no {PACKAGE_MANIFEST} — not a Headcount package")
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as error:
        raise PackageError(f"{manifest_path}: unreadable package manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise PackageError(f"{manifest_path}: package manifest is not an object")
    if manifest.get("format") != PACKAGE_FORMAT:
        raise PackageError(f"{manifest_path}: format {manifest.get('format')!r} is not "
                           f"{PACKAGE_FORMAT!r}")
    missing_fields = [f for f in REQUIRED_PACKAGE_FIELDS if f not in manifest]
    if missing_fields:
        raise PackageError(f"{manifest_path}: missing field(s) {', '.join(missing_fields)}")
    declared = manifest["files"]
    if not isinstance(declared, dict) or not declared:
        raise PackageError(f"{manifest_path}: 'files' must be a non-empty object")
    for rel in declared:
        _check_relpath(rel)

    present, links = _walk_files(package_dir)
    if links:
        raise PackageError(f"{package_dir}: symlink(s) in package: {', '.join(links[:5])}")
    present = [p for p in present if p != PACKAGE_MANIFEST]
    missing = sorted(set(declared) - set(present))
    if missing:
        raise PackageError(f"{package_dir}: incomplete package, missing "
                           f"{', '.join(missing[:5])}")
    extra = sorted(set(present) - set(declared))
    if extra:
        raise PackageError(f"{package_dir}: file(s) not listed in the manifest: "
                           f"{', '.join(extra[:5])}")
    altered = [rel for rel in sorted(declared)
               if sha256_file(os.path.join(package_dir, rel)) != declared[rel]]
    if altered:
        raise PackageError(f"{package_dir}: content does not match the manifest hash for "
                           f"{', '.join(altered[:5])} — the package was altered after it "
                           f"was built")
    return manifest


def read_install_manifest(target_dir):
    """The record of what Headcount owns in this target, or None if it owns nothing."""
    path = os.path.join(target_dir, INSTALL_MANIFEST)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as error:
        raise InstallError(f"{path}: unreadable install manifest: {error}. Move it aside to "
                           f"treat this target as unmanaged.") from error
    if not isinstance(manifest, dict) or manifest.get("format") != INSTALL_FORMAT:
        raise InstallError(f"{path}: not a {INSTALL_FORMAT} manifest")
    if not isinstance(manifest.get("files"), dict):
        raise InstallError(f"{path}: install manifest has no 'files' object")
    return manifest


def _managed(target_dir):
    manifest = read_install_manifest(target_dir)
    return manifest, dict(manifest["files"]) if manifest else {}


def _unmanaged_files(target_dir, managed):
    present, _ = _walk_files(target_dir, skip_names=(BACKUP_DIR,))
    return [rel for rel in present if rel != INSTALL_MANIFEST and rel not in managed]


def plan_install(package_dir, target_dir, operation=INSTALL):
    """Non-destructive. Reads the package and the target, writes nothing, returns the plan."""
    package = verify_package(package_dir)
    manifest, managed = _managed(target_dir)
    if operation == UPDATE and manifest is None:
        raise InstallError(f"{target_dir}: no Headcount install to update "
                           f"({INSTALL_MANIFEST} is missing) — install instead")

    adds, replacements, collisions = [], [], []
    for rel in sorted(package["files"]):
        destination = os.path.join(target_dir, rel)
        if not os.path.exists(destination):
            adds.append(rel)
        elif rel not in managed:
            collisions.append(Collision(rel, UNMANAGED_EXISTS, True))
        elif sha256_file(destination) == managed[rel]:
            replacements.append(rel)
        else:
            collisions.append(Collision(rel, LOCALLY_MODIFIED, operation == INSTALL))

    removals = []
    if operation == UPDATE:
        # Files the previous package installed and this one no longer contains. Dropping them
        # is the point of an update; dropping one the user has edited is not.
        for rel in sorted(set(managed) - set(package["files"])):
            destination = os.path.join(target_dir, rel)
            if not os.path.exists(destination):
                continue
            if sha256_file(destination) == managed[rel]:
                removals.append(rel)
            else:
                collisions.append(Collision(rel, LOCALLY_MODIFIED, False))

    collisions.sort(key=lambda c: c.path)
    return InstallPlan(
        operation=operation,
        target_dir=target_dir,
        package_dir=package_dir,
        adds=adds,
        replacements=replacements,
        removals=removals,
        collisions=collisions,
        unmanaged=_unmanaged_files(target_dir, managed),
        backup_required=bool(collisions),
        headcount_version=package["headcount_version"],
        runtime=package["runtime"],
        build_id=package["build_id"],
        source_commit=package["source_commit"],
        package_files=dict(package["files"]),
    )


def plan_update(package_dir, target_dir):
    return plan_install(package_dir, target_dir, operation=UPDATE)


def plan_uninstall(target_dir):
    """Remove exactly what the manifest records. Everything else in the target is not ours."""
    manifest, managed = _managed(target_dir)
    if manifest is None:
        raise InstallError(f"{target_dir}: no Headcount install found "
                           f"({INSTALL_MANIFEST} is missing)")
    removals, collisions = [], []
    for rel in sorted(managed):
        destination = os.path.join(target_dir, rel)
        if not os.path.exists(destination):
            continue  # already gone; nothing to remove and nothing to warn about
        if sha256_file(destination) == managed[rel]:
            removals.append(rel)
        else:
            collisions.append(Collision(rel, LOCALLY_MODIFIED, False))
    return InstallPlan(
        operation=UNINSTALL,
        target_dir=target_dir,
        removals=removals,
        collisions=collisions,
        unmanaged=_unmanaged_files(target_dir, managed),
        backup_required=bool(collisions),
        headcount_version=manifest.get("headcount_version"),
        runtime=manifest.get("runtime"),
        build_id=manifest.get("build_id"),
        source_commit=manifest.get("source_commit"),
    )


def _ensure_directory(path):
    if os.path.exists(path) and not os.path.isdir(path):
        raise InstallError(f"{path}: target exists and is not a directory")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as error:
        raise InstallError(f"{path}: cannot create target directory: {error}") from error


def _timestamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _backup(target_dir, relpaths):
    """Copy the current bytes of the named paths under a timestamped directory in the target.

    Only content Headcount did not write is copied. An unmodified managed file is byte-for-byte
    reproducible from the package, so backing it up would only make the backup harder to read.
    """
    stamp = _timestamp()
    directory = os.path.join(target_dir, BACKUP_DIR, stamp)
    suffix = 2
    while os.path.exists(directory):
        directory = os.path.join(target_dir, BACKUP_DIR, f"{stamp}-{suffix}")
        suffix += 1
    for rel in relpaths:
        source = os.path.join(target_dir, rel)
        if not os.path.exists(source):
            continue
        destination = os.path.join(directory, rel)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
    return directory


def _place(staged, destination):
    """Atomic on the same filesystem, which staging inside the target guarantees."""
    os.replace(staged, destination)


def _prune_parents(target_dir, relpaths):
    """Remove directories emptied by a removal, and only those. A user's empty directory that
    never held a managed file is left alone."""
    root = os.path.abspath(target_dir)
    for rel in relpaths:
        parent = os.path.dirname(os.path.abspath(os.path.join(target_dir, rel)))
        while parent != root and parent.startswith(root + os.sep):
            try:
                os.rmdir(parent)
            except OSError:
                break
            parent = os.path.dirname(parent)


def _write_install_manifest(target_dir, plan, files, previous):
    payload = {
        "format": INSTALL_FORMAT,
        "headcount_version": plan.headcount_version,
        "source_commit": plan.source_commit,
        "build_id": plan.build_id,
        "runtime": plan.runtime,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": dict(sorted(files.items())),
    }
    if previous and previous.get("installed_at"):
        payload["previous_installed_at"] = previous["installed_at"]
    path = os.path.join(target_dir, INSTALL_MANIFEST)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(temporary, path)


def _apply(plan, force, backup, dry_run):
    if plan.blocking and not force:
        detail = ", ".join(f"{c.path} ({c.reason})" for c in plan.blocking[:5])
        raise CollisionError(
            f"{plan.target_dir}: refusing to {plan.operation} over content Headcount did not "
            f"write: {detail}. Nothing was changed. Re-run with force to overwrite, which "
            f"copies the current files into a timestamped backup first.")

    resolved = list(plan.collisions) if force else []
    skipped = [] if force else sorted(c.path for c in plan.collisions)
    overwrites = [c.path for c in resolved if c.path in plan.package_files]
    forced_removals = [c.path for c in resolved if c.path not in plan.package_files]

    to_write = sorted(set(plan.adds) | set(plan.replacements) | set(overwrites))
    to_remove = sorted(set(plan.removals) | set(forced_removals))
    at_risk = sorted(c.path for c in resolved)

    if dry_run:
        return InstallResult(plan=plan, dry_run=True, written=to_write, removed=to_remove,
                             skipped=skipped, backup_dir=None)

    _ensure_directory(plan.target_dir)
    previous, managed = _managed(plan.target_dir)
    staging = None
    backup_dir = None
    try:
        if backup and at_risk:
            backup_dir = _backup(plan.target_dir, at_risk)
        if to_write:
            # Everything is copied and rehashed before anything is moved, so a package that
            # changes underneath us is caught while the target is still untouched.
            staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=plan.target_dir)
            staged = {}
            for index, rel in enumerate(to_write):
                temporary = os.path.join(staging, f"{index:06d}")
                shutil.copy2(os.path.join(plan.package_dir, rel), temporary)
                if sha256_file(temporary) != plan.package_files[rel]:
                    raise InstallError(f"{rel}: package content changed while staging")
                staged[rel] = temporary
            for rel in to_write:
                destination = os.path.join(plan.target_dir, rel)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                _place(staged[rel], destination)
        for rel in to_remove:
            destination = os.path.join(plan.target_dir, rel)
            if os.path.exists(destination):
                os.remove(destination)
        _prune_parents(plan.target_dir, to_remove)

        files = dict(managed)
        for rel in to_write:
            files[rel] = plan.package_files[rel]
        for rel in to_remove:
            files.pop(rel, None)
        # A skipped file keeps the hash we originally recorded, never the edited one: adopting
        # the user's bytes as ours would let the next update overwrite them silently.
        files = {rel: digest for rel, digest in files.items()
                 if os.path.exists(os.path.join(plan.target_dir, rel))}
        if plan.operation == UNINSTALL and not files:
            manifest_path = os.path.join(plan.target_dir, INSTALL_MANIFEST)
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
        else:
            _write_install_manifest(plan.target_dir, plan, files, previous)
    except OSError as error:
        raise InstallError(f"{plan.target_dir}: {plan.operation} failed: {error}") from error
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)

    return InstallResult(plan=plan, dry_run=False, written=to_write, removed=to_remove,
                         skipped=skipped, backup_dir=backup_dir)


def _resolve_plan(plan, operation, package_dir, target_dir):
    """Always re-plan from disk. A plan is a description, not a permit: the one handed in may
    have been produced minutes ago, and the target can have changed since."""
    if plan is not None:
        operation = plan.operation
        package_dir = plan.package_dir
        target_dir = plan.target_dir
    if not target_dir:
        raise InstallError("a target directory is required")
    if operation == UNINSTALL:
        return plan_uninstall(target_dir)
    if not package_dir:
        raise InstallError("a package directory is required")
    return plan_install(package_dir, target_dir, operation=operation)


def apply_install(plan=None, *, package_dir=None, target_dir=None, force=False, backup=True,
                  dry_run=False):
    """Install a package into a target. Refuses on any collision unless force is given."""
    return _apply(_resolve_plan(plan, INSTALL, package_dir, target_dir), force, backup, dry_run)


def update_install(plan=None, *, package_dir=None, target_dir=None, force=False, backup=True,
                   dry_run=False):
    """Move an existing install to a new package: replace what is ours, drop what the package
    no longer contains, leave everything else, and report what was left alone."""
    return _apply(_resolve_plan(plan, UPDATE, package_dir, target_dir), force, backup, dry_run)


def uninstall(target_dir=None, *, plan=None, force=False, backup=True, dry_run=False):
    """Remove the files the manifest records, and nothing else."""
    return _apply(_resolve_plan(plan, UNINSTALL, None, target_dir), force, backup, dry_run)
