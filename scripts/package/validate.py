#!/usr/bin/env python3
"""Check a built package against its own manifest and against the tree it claims to be built from.

    python3 scripts/package/validate.py dist/codex
    python3 scripts/package/validate.py dist/codex --repo ../headcount

Independent of the builder by construction: it reads the package from disk and the canonical tree
from disk, and compares them. It never calls the builder, so a builder that writes the wrong
bytes cannot also certify them — and a package that arrived by some other route (downloaded,
edited, partially extracted) is checkable with the same command.

Every problem is reported, not just the first: a package with three missing skills should say so
once, rather than three runs later.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

EXPECTED_RUNTIME = "codex"
REQUIRED_KEYS = {"format", "runtime", "headcount_version", "source_commit", "build_id",
                 "skill_count", "agent_count", "files"}
GENERATED_DOCS = ("AGENTS.md", "README.md")


def disk_files(package):
    """{relative path: sha256} for every file in the package except the manifest itself."""
    found = {}
    for base, _, names in os.walk(package):
        for name in names:
            path = os.path.join(base, name)
            relative = os.path.relpath(path, package).replace(os.sep, "/")
            if relative == common.MANIFEST_NAME:
                continue
            found[relative] = common.sha256_file(path)
    return found


def count_skills(paths):
    """Skill directories are those holding a SKILL.md directly under skills/<name>/."""
    return len({p.split("/")[1] for p in paths
                if p.startswith("skills/") and p.count("/") == 2
                and p.endswith("/" + common.SKILL_FILE)})


def count_agents(paths):
    return len([p for p in paths if p.startswith("agents/") and p.count("/") == 1
                and p.endswith(".md")])


def check_manifest_shape(manifest, problems):
    missing = sorted(REQUIRED_KEYS - set(manifest))
    if missing:
        problems.append(f"{common.MANIFEST_NAME}: missing key(s): {', '.join(missing)}")
    if manifest.get("format") != common.PACKAGE_FORMAT:
        problems.append(f"{common.MANIFEST_NAME}: format is {manifest.get('format')!r}, "
                        f"expected {common.PACKAGE_FORMAT!r}")
    if manifest.get("runtime") != EXPECTED_RUNTIME:
        problems.append(f"{common.MANIFEST_NAME}: runtime is {manifest.get('runtime')!r}, "
                        f"expected {EXPECTED_RUNTIME!r}")
    if not isinstance(manifest.get("files"), dict):
        problems.append(f"{common.MANIFEST_NAME}: files must be an object of path to sha256")
        return False
    return True


def check_against_manifest(manifest, on_disk, problems):
    listed = manifest["files"]
    if common.MANIFEST_NAME in listed:
        problems.append(f"{common.MANIFEST_NAME}: the manifest must not list itself")
    for path in sorted(set(listed) - set(on_disk)):
        problems.append(f"{path}: listed in the manifest but not in the package")
    for path in sorted(set(on_disk) - set(listed)):
        problems.append(f"{path}: in the package but not listed in the manifest")
    for path in sorted(set(listed) & set(on_disk)):
        if listed[path] != on_disk[path]:
            problems.append(f"{path}: content does not match its sha256 in the manifest")
    for doc in GENERATED_DOCS:
        if doc not in on_disk:
            problems.append(f"{doc}: missing from the package")

    expected = common.build_id(listed)
    if manifest.get("build_id") != expected:
        problems.append(f"{common.MANIFEST_NAME}: build_id {manifest.get('build_id')!r} does not "
                        f"match the files it lists (recomputed {expected!r})")

    for label, counter, key in (("skill", count_skills, "skill_count"),
                                ("agent", count_agents, "agent_count")):
        listed_count = counter(listed)
        if manifest.get(key) != listed_count:
            problems.append(f"{common.MANIFEST_NAME}: {key} is {manifest.get(key)!r} but the "
                            f"manifest lists {listed_count} {label}(s)")


def check_against_canonical(repo, manifest, on_disk, problems):
    """The package must be a lossless projection of the canonical tree, in both directions."""
    skills = common.skills(repo)
    charters = common.charters(repo)

    for name, paths in sorted(common.collisions(skills).items()):
        problems.append(f"skills/{name}: {len(paths)} departments carry this bare name "
                        f"({', '.join(paths)}) — a flat package cannot represent both")

    expected = {}
    for skill in skills:
        for relative in skill.files:
            expected[f"skills/{skill.name}/{relative}"] = os.path.join(
                skill.source, *relative.split("/"))
    for charter in charters:
        expected[f"agents/{charter.name}.md"] = charter.source

    for path in sorted(set(expected) - set(on_disk)):
        problems.append(f"{path}: missing from the package (canonical source exists)")
    for path in sorted(set(on_disk) - set(expected) - set(GENERATED_DOCS)):
        problems.append(f"{path}: in the package with no canonical source")
    for path in sorted(set(expected) & set(on_disk)):
        if common.sha256_file(expected[path]) != on_disk[path]:
            problems.append(f"{path}: content differs from its canonical source")

    if manifest is not None:
        for key, actual in (("skill_count", len(skills)), ("agent_count", len(charters))):
            if key in manifest and manifest[key] != actual:
                problems.append(f"{common.MANIFEST_NAME}: {key} is {manifest[key]!r} but the "
                                f"canonical tree has {actual}")
        version = common.load_registry(repo)["marketplace"]["version"]
        if manifest.get("headcount_version") != version:
            problems.append(f"{common.MANIFEST_NAME}: headcount_version is "
                            f"{manifest.get('headcount_version')!r}, canonical registry says "
                            f"{version!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a built headcount package.")
    parser.add_argument("package", help="the package directory to check")
    parser.add_argument("--repo", default=".", help="source repository root (default: .)")
    args = parser.parse_args(argv)

    problems = []
    if not os.path.isdir(args.package):
        print(f"  {args.package}: not a directory")
        print("codex package: 0 skills, 0 agents, 1 problems")
        return 1

    on_disk = disk_files(args.package)
    manifest_path = os.path.join(args.package, common.MANIFEST_NAME)
    manifest = None
    if not os.path.exists(manifest_path):
        problems.append(f"{common.MANIFEST_NAME}: missing from the package")
    else:
        try:
            with open(manifest_path, encoding="utf-8") as handle:
                manifest = json.load(handle)
        except ValueError as e:
            problems.append(f"{common.MANIFEST_NAME}: not valid JSON: {e}")
        else:
            if not isinstance(manifest, dict):
                problems.append(f"{common.MANIFEST_NAME}: top level must be an object")
                manifest = None
            elif check_manifest_shape(manifest, problems):
                check_against_manifest(manifest, on_disk, problems)

    check_against_canonical(args.repo, manifest, on_disk, problems)

    for problem in problems:
        print(f"  {problem}")
    print(f"codex package: {count_skills(on_disk)} skills, {count_agents(on_disk)} agents, "
          f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
