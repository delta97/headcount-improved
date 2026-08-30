#!/usr/bin/env python3
"""Build the Codex package: the canonical tree projected into a flat Agent-Skills layout.

    python3 scripts/package/codex.py --output dist/codex
    python3 scripts/package/codex.py --output dist/codex --check   # CI: fail if it has drifted
    python3 scripts/package/codex.py --repo ../headcount --output dist/codex --force

The package is a derived artifact and is never a second source of truth: skills and charters are
copied byte for byte, and AGENTS.md and README.md are generated from config/departments.json
rather than copied from the repository's own documents, which describe a different runtime.

Two properties the installer depends on:

  * The build is deterministic. build_id is a digest over content alone, so two builds of one
    commit are byte-identical and `--check` can state drift as a fact rather than a suspicion.
  * The build is total or absent. Every failure is raised before the first byte is written, and
    the finished package is moved into place with one rename.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

RUNTIME = "codex"


def _table(rows, header):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + [
        "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]


def agents_md(depts, by_department, skill_total, charter_total):
    """Instructions for the runtime that loads this package, from registry data."""
    out = [
        "# headcount",
        "",
        f"{skill_total} skills and {charter_total} agent charters from the headcount department",
        "library, built for a runtime with a single flat skill namespace.",
        "",
        "Generated from the canonical repository. Nothing here is edited in place: change the",
        "source tree and rebuild, or the next build discards the edit.",
        "",
        "## Using a skill",
        "",
        "Each directory under `skills/` holds one skill — a `SKILL.md` whose frontmatter states what",
        "it is for, plus any references or scripts it needs. Load the one whose description matches",
        "the request; the descriptions are written to discriminate between neighbors, so the closest",
        "match is the intended one.",
        "",
        "The source repository addresses a skill as `department:skill` (`finance:unit-economics`).",
        "That namespace does not survive flattening, so each skill appears here under its bare name",
        "(`unit-economics`). The tables below carry the department attribution the name no longer",
        "does.",
        "",
        "## Departments",
        "",
    ]
    out += _table([(d["id"], d["title"], d["executive"], d["category"],
                    str(len(by_department.get(d["id"], []))))
                   for d in depts],
                  ("Department", "Function", "Executive", "Category", "Skills"))
    out += [
        "",
        "## Charters",
        "",
        "`agents/<name>.md` holds one charter per department agent: its remit, the surface it owns,",
        "and what it refuses. Where the runtime supports delegation, a charter is what a department",
        "is delegated as.",
        "",
        "## Skills by department",
        "",
    ]
    for d in depts:
        names = by_department.get(d["id"], [])
        if not names:
            continue
        out += [f"**{d['title']}** ({d['executive']}) — " + ", ".join(f"`{n}`" for n in names), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def readme_md(depts, by_department, skill_total, charter_total, version, commit):
    """What the package is, where it came from, and how to check it — from registry data."""
    out = [
        "# headcount — codex package",
        "",
        "The headcount department library built for a Codex-style Agent-Skills runtime:",
        f"{skill_total} skills across {len(depts)} departments, plus {charter_total} agent charters.",
        "",
        f"- headcount version: `{version}`",
        f"- source commit: `{commit}`",
        f"- package format: `{common.PACKAGE_FORMAT}`",
        "",
        "## Layout",
        "",
        "```",
        "headcount-package.json   manifest: format, provenance, and a sha256 for every file",
        "AGENTS.md                instructions for the runtime that loads this package",
        "README.md                this file",
        "agents/<name>.md         one charter per department agent",
        "skills/<skill>/          one directory per skill: SKILL.md and anything it references",
        "```",
        "",
        "Skill directories are flat here. In the source repository a skill lives at",
        "`plugins/<department>/skills/<skill>/` and is addressed as `department:skill`; a runtime",
        "with one skill namespace cannot express that, so the department survives as attribution in",
        "the table below rather than as part of the address.",
        "",
        "## Departments",
        "",
    ]
    out += _table([(d["id"], d["title"], d["executive"], d["category"],
                    str(len(by_department.get(d["id"], []))), d["description"])
                   for d in depts],
                  ("Department", "Function", "Executive", "Category", "Skills", "What it covers"))
    out += [
        "",
        "## Verifying this package",
        "",
        "`headcount-package.json` carries a sha256 for every file and a `build_id` derived from",
        "those digests alone. From the source repository:",
        "",
        "```",
        "python3 scripts/package/validate.py <this directory>",
        "```",
        "",
        "It reports every difference between the package, its manifest, and the canonical tree it",
        "claims to be a build of. Because the build depends on content and not on when it ran, two",
        "builds of one commit are identical, and a rebuild is a diffable statement of what changed.",
        "",
    ]
    return "\n".join(out).rstrip("\n") + "\n"


def payload(repo):
    """{package-relative path: bytes} for everything except the manifest.

    Raises before returning if the canonical tree cannot be represented in a flat namespace, so
    no partial package is ever written.
    """
    depts = common.departments(repo)
    skills = common.skills(repo)
    charters = common.charters(repo)

    duplicates = common.collisions(skills)
    if duplicates:
        detail = "\n".join(f"  {name}:\n" + "\n".join(f"    {p}" for p in paths)
                           for name, paths in sorted(duplicates.items()))
        raise common.PackageError(
            f"codex package: {len(duplicates)} skill name(s) carried by more than one department, "
            "which a flattened package cannot represent:\n" + detail + "\n"
            "  Claude Code addresses a skill as department:skill, so these coexist in the canonical\n"
            "  tree by design (D32). An Agent-Skills runtime has a single flat skill namespace, so\n"
            "  both would land at skills/<name>/ and one would overwrite the other.\n"
            "  Rename one skill of each pair, or leave one department out of this build.")

    files = {}
    for skill in skills:
        for relative in skill.files:
            with open(os.path.join(skill.source, *relative.split("/")), "rb") as handle:
                files[f"skills/{skill.name}/{relative}"] = handle.read()
    for charter in charters:
        with open(charter.source, "rb") as handle:
            files[f"agents/{charter.name}.md"] = handle.read()

    by_department = {}
    for skill in skills:
        by_department.setdefault(skill.department, []).append(skill.name)
    version = common.load_registry(repo)["marketplace"]["version"]
    counts = (len(skills), len(charters))
    files["AGENTS.md"] = agents_md(depts, by_department, *counts).encode("utf-8")
    files["README.md"] = readme_md(depts, by_department, *counts, version,
                                   common.source_commit(repo)).encode("utf-8")
    return files, len(skills), len(charters), version


def manifest_text(repo, files, skill_count, agent_count, version):
    digests = {path: common.sha256_bytes(data) for path, data in files.items()}
    manifest = {
        "format": common.PACKAGE_FORMAT,
        "runtime": RUNTIME,
        "headcount_version": version,
        "source_commit": common.source_commit(repo),
        "build_id": common.build_id(digests),
        "skill_count": skill_count,
        "agent_count": agent_count,
        "files": digests,
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def write_into(directory, files, manifest):
    for path in sorted(files):
        target = os.path.join(directory, *path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(files[path])
    with open(os.path.join(directory, common.MANIFEST_NAME), "w", encoding="utf-8") as handle:
        handle.write(manifest)


def read_tree(directory):
    """{relative path: bytes} for a package on disk — {} if it is not there at all."""
    found = {}
    if not os.path.isdir(directory):
        return found
    for base, _, names in os.walk(directory):
        for name in names:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, directory).replace(os.sep, "/")] = handle.read()
    return found


def publish(output, files, manifest, force):
    """Write the package beside the target and move it into place with one rename.

    A half-written package is worse than none: an installer cannot tell it from a whole one.
    """
    if os.path.exists(output) and not os.path.isdir(output):
        raise common.PackageError(f"codex package: {output} exists and is not a directory")
    if os.path.isdir(output) and os.listdir(output) and not force:
        raise common.PackageError(
            f"codex package: {output} is not empty — refusing to overwrite it.\n"
            "  Pass --force to replace its contents, or choose another --output directory.")
    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".codex-package-", dir=parent)
    try:
        write_into(staging, files, manifest)
        if os.path.isdir(output):
            shutil.rmtree(output)
        os.replace(staging, output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def check(output, files, manifest):
    """Report every difference between a fresh build and the package already on disk."""
    staging = tempfile.mkdtemp(prefix=".codex-package-check-")
    try:
        write_into(staging, files, manifest)
        fresh = read_tree(staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    on_disk = read_tree(output)

    problems = []
    for path in sorted(set(fresh) - set(on_disk)):
        problems.append(f"{path} is missing from the package")
    for path in sorted(set(on_disk) - set(fresh)):
        problems.append(f"{path} is in the package but not in a fresh build")
    for path in sorted(set(fresh) & set(on_disk)):
        if fresh[path] != on_disk[path]:
            problems.append(f"{path} differs from a fresh build")
    for problem in problems:
        print(f"  {problem}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the headcount Codex package.")
    parser.add_argument("--output", required=True, help="directory to write the package into")
    parser.add_argument("--repo", default=".", help="source repository root (default: .)")
    parser.add_argument("--force", action="store_true",
                        help="replace a non-empty --output directory")
    parser.add_argument("--check", action="store_true",
                        help="compare --output against a fresh build and exit 1 on any drift")
    args = parser.parse_args(argv)

    files, skill_count, agent_count, version = payload(args.repo)
    manifest = manifest_text(args.repo, files, skill_count, agent_count, version)

    if args.check:
        problems = check(args.output, files, manifest)
        if problems:
            print(f"codex package: {len(problems)} difference(s) — run: "
                  f"python3 scripts/package/codex.py --output {args.output} --force")
            return 1
        print(f"codex package is current — {skill_count} skills, {agent_count} agents")
        return 0

    publish(args.output, files, manifest, args.force)
    print(f"codex package: {skill_count} skills, {agent_count} agents written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
