"""The canonical tree as a package builder sees it: departments, skills, charters, digests.

One model, shared by the builder and the validator, so the two cannot disagree about what the
repository contains — a validator that re-derives "what should be in the package" from its own
reading of the tree would pass a package the builder produced wrongly, and fail one it produced
correctly, for reasons nobody could tell apart.

The registry loader travels with this module rather than being read out of the target tree: a
package can be built from any checkout by pointing --repo at it, and that checkout supplies
registry *data* (config/departments.json), never registry *code*. So the coupling to a source
tree is exactly three things:

    config/departments.json          department metadata, loaded through scripts/registry.py
    plugins/<id>/skills/<skill>/     skill directories, copied whole
    .claude/agents/<name>.md         agent charters, copied byte for byte

Paths in packages are POSIX-separated on every platform, because they are keys in a manifest
that is compared across machines, not local filesystem paths.
"""
import collections
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import registry

MANIFEST_NAME = "headcount-package.json"
PACKAGE_FORMAT = "headcount-package/1"
SKILL_FILE = "SKILL.md"
CHARTER_DIR = os.path.join(".claude", "agents")
PLUGIN_DIR = "plugins"


class PackageError(SystemExit):
    """Raised (as an exit) so a tree the package format cannot represent stops the build."""


Skill = collections.namedtuple("Skill", "department name source files")
Charter = collections.namedtuple("Charter", "name source")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_id(files):
    """A digest of content alone: sorted 'path\\nsha256\\n' lines over {path: sha256}.

    Nothing time-dependent enters it, so two builds of one tree carry one build id, and any
    difference in the payload changes it.
    """
    lines = "".join(f"{path}\n{files[path]}\n" for path in sorted(files))
    return sha256_bytes(lines.encode("utf-8"))


def load_registry(repo):
    """The registry document, shape-validated by scripts/registry.py."""
    return registry.load(os.path.join(repo, registry.REGISTRY_PATH))


def departments(repo):
    """Registry departments, rank-sorted, cross-checked against the plugin tree.

    A department on disk but not in the registry would ship its skills with no entry in the
    generated documents; a registry entry with no directory would document skills that are not
    in the package. Both are hard errors rather than quiet asymmetries.
    """
    depts = load_registry(repo)["departments"]
    plugins = os.path.join(repo, PLUGIN_DIR)
    on_disk = {name for name in os.listdir(plugins)
               if os.path.isdir(os.path.join(plugins, name))} if os.path.isdir(plugins) else set()
    listed = {d["id"] for d in depts}
    extra = sorted(on_disk - listed)
    if extra:
        raise PackageError("package: plugins/" + ", plugins/".join(extra)
                           + " exist but have no registry entry — add them to "
                           + registry.REGISTRY_PATH)
    missing = sorted(listed - on_disk)
    if missing:
        raise PackageError("package: the registry lists " + ", ".join(missing)
                           + " but plugins/<id>/ does not exist for them — fix "
                           + registry.REGISTRY_PATH)
    return depts


def _files_under(root):
    """Every file under root, as sorted POSIX paths relative to it."""
    found = []
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            found.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return sorted(found)


def skills(repo):
    """Every canonical skill, sorted by (department, name), with its whole directory listed.

    A skill is a directory holding SKILL.md; anything beside it — references/, scripts/ — is
    part of the skill and travels with it.
    """
    found = []
    plugins = os.path.join(repo, PLUGIN_DIR)
    if not os.path.isdir(plugins):
        return found
    for department in sorted(os.listdir(plugins)):
        skills_dir = os.path.join(plugins, department, "skills")
        if not os.path.isdir(skills_dir):
            continue
        for name in sorted(os.listdir(skills_dir)):
            source = os.path.join(skills_dir, name)
            if not os.path.isfile(os.path.join(source, SKILL_FILE)):
                continue
            found.append(Skill(department, name, source, _files_under(source)))
    return found


def charters(repo):
    """Every agent charter in .claude/agents/, sorted by file name."""
    found = []
    directory = os.path.join(repo, CHARTER_DIR)
    if not os.path.isdir(directory):
        return found
    for name in sorted(os.listdir(directory)):
        if name.endswith(".md"):
            found.append(Charter(name[: -len(".md")], os.path.join(directory, name)))
    return found


def canonical_path(skill, relative=""):
    """The repository-relative path of a skill directory, or of one file inside it."""
    base = f"{PLUGIN_DIR}/{skill.department}/skills/{skill.name}"
    return f"{base}/{relative}" if relative else base


def collisions(skill_list):
    """{bare name: [canonical paths]} for names carried by more than one department.

    Legal in the canonical tree, which addresses skills as department:skill (D32), and
    unrepresentable in a package with a single flat skill namespace — so every flattening
    builder has to refuse it rather than silently drop one of the two.
    """
    by_name = collections.defaultdict(list)
    for skill in skill_list:
        by_name[skill.name].append(canonical_path(skill))
    return {name: sorted(paths) for name, paths in by_name.items() if len(paths) > 1}


def source_commit(repo):
    """The commit the package was built from, or 'unknown' outside a git work tree.

    Only reported when repo is itself the top of a work tree: a fixture tree that happens to sit
    inside some unrelated checkout must not be stamped with that checkout's commit.
    """
    try:
        top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
        head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True)
    except OSError:
        return "unknown"
    if top.returncode != 0 or head.returncode != 0:
        return "unknown"
    if os.path.realpath(top.stdout.strip()) != os.path.realpath(repo):
        return "unknown"
    return head.stdout.strip() or "unknown"
