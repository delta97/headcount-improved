#!/usr/bin/env python3
"""Cross-check the canonical registry against everything that must agree with it.

config/departments.json is authoritative for department metadata, but two files still hold
copies Claude Code requires: each plugin's .claude-plugin/plugin.json (hand-written, inside
that department's write surface) and .claude-plugin/marketplace.json (generated). This check
makes the remaining duplication safe: a contributor cannot add a plugin and forget the
registry, change a description in one place only, point a marketplace entry at a missing
directory, or classify the same department two different ways. Before it existed, five such
divergences were live in the tree and nothing failed.

Run from the repository root:  python3 scripts/validate-catalog.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry

REPO_URL = "https://github.com/cbrock84/headcount"
SURFACE_MAP = "docs/AGENT-SURFACES.md"
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# The category taxonomy is closed on purpose: a typo'd category would silently start a new
# one. Adding a genuine category means adding it here, in the same change.
CATEGORIES = {
    "executive", "technology", "product", "marketing", "demand-generation", "revenue",
    "finance", "operations", "people", "legal-risk", "security", "customer-experience",
    "data-analytics", "corporate-strategy",
}
MANIFEST_FIELDS = {"name", "description", "version", "author", "repository", "keywords"}


def parse_roster(text):
    """Rows from the ```roster block: [(id, class, status, authority-or-None)]."""
    block = re.search(r"^```roster\n(.*?)^```$", text, re.S | re.M)
    if not block:
        return None
    rows = []
    for line in block.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split()
        rows.append((cols + [None] * 4)[:4])
    return rows


def main():
    problems = []

    try:
        data = registry.load()
    except SystemExit as e:
        print(f"  {e}")
        print("catalog: 1 problem")
        return 1
    depts = data["departments"]
    by_id = {d["id"]: d for d in depts}
    owner_name = data["marketplace"]["owner"].get("name", "")

    # ── The registry's own semantics ──────────────────────────────────────────────
    for d in depts:
        ident = d["id"]
        if not SLUG.fullmatch(ident):
            problems.append(f"registry: id {ident!r} is not lowercase-hyphenated")
        if not SEMVER.fullmatch(d["version"]):
            problems.append(f"registry: {ident} version {d['version']!r} is not MAJOR.MINOR.PATCH")
        if d["category"] not in CATEGORIES:
            problems.append(f"registry: {ident} category {d['category']!r} is not a known category")
        if len(d["description"].strip()) < 40:
            problems.append(f"registry: {ident} description too thin to describe a department")
        if "\n" in d["description"]:
            problems.append(f"registry: {ident} description must be a single line")
        if not d["keywords"]:
            problems.append(f"registry: {ident} has no keywords")
        for k in d["keywords"]:
            if not SLUG.fullmatch(k):
                problems.append(f"registry: {ident} keyword {k!r} is not lowercase-hyphenated")
        if not d["title"].strip() or not d["executive"].strip():
            problems.append(f"registry: {ident} title/executive must be non-empty")

    # ── Registry ↔ plugin tree, both directions ──────────────────────────────────
    on_disk = {p for p in os.listdir("plugins") if os.path.isdir(os.path.join("plugins", p))}
    for extra in sorted(on_disk - set(by_id)):
        problems.append(f"plugins/{extra}/ exists but has no registry entry — add it to config/departments.json")
    for missing in sorted(set(by_id) - on_disk):
        problems.append(f"registry lists {missing!r} but plugins/{missing}/ does not exist")

    # ── Each plugin manifest against the registry ────────────────────────────────
    for ident in sorted(set(by_id) & on_disk):
        path = f"plugins/{ident}/.claude-plugin/plugin.json"
        if not os.path.exists(path):
            problems.append(f"{path} is missing")
            continue
        try:
            man = json.load(open(path, encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{path}: not valid JSON: {e}")
            continue
        missing = sorted(MANIFEST_FIELDS - set(man))
        if missing:
            problems.append(f"{path}: missing field(s): {', '.join(missing)}")
        unknown = sorted(set(man) - MANIFEST_FIELDS)
        if unknown:
            problems.append(f"{path}: unknown field(s): {', '.join(unknown)}")
        d = by_id[ident]
        checks = [
            ("name", man.get("name"), ident),
            ("description", man.get("description"), d["description"]),
            ("version", man.get("version"), d["version"]),
            ("keywords", man.get("keywords"), d["keywords"]),
            ("repository", man.get("repository"), REPO_URL),
        ]
        for field, actual, expected in checks:
            if field in man and actual != expected:
                problems.append(f"{path}: {field} disagrees with the registry\n"
                                f"      manifest: {actual!r}\n      registry: {expected!r}")
        author = man.get("author")
        if "author" in man and (not isinstance(author, dict) or author.get("name") != owner_name):
            problems.append(f"{path}: author must be {{\"name\": {owner_name!r}}}")

    # ── The marketplace file resolves (content parity is build-marketplace --check) ──
    mp_path = ".claude-plugin/marketplace.json"
    try:
        mp = json.load(open(mp_path, encoding="utf-8"))
        names = [p.get("name") for p in mp.get("plugins", [])]
        if sorted(names) != sorted(by_id):
            problems.append(f"{mp_path}: plugin set differs from the registry — "
                            "run: python3 scripts/build-marketplace.py")
        for p in mp.get("plugins", []):
            src = p.get("source", "")
            if not os.path.isdir(src):
                problems.append(f"{mp_path}: {p.get('name')} source {src!r} does not exist")
    except (OSError, ValueError) as e:
        problems.append(f"{mp_path}: unreadable: {e}")

    # ── Registry ↔ roster ↔ charters ─────────────────────────────────────────────
    # agent-guard owns roster↔charter coherence; this adds the registry to that triangle so a
    # department cannot be installable without being dispatchable, or vice versa.
    rows = parse_roster(open(SURFACE_MAP, encoding="utf-8").read()) if os.path.exists(SURFACE_MAP) else None
    if rows is None:
        problems.append(f"{SURFACE_MAP}: no ```roster block found")
    else:
        roster = {r[0]: r for r in rows}
        for ident, d in sorted(by_id.items()):
            row = roster.get(ident)
            if row is None:
                problems.append(f"roster: registry department {ident!r} has no roster row")
                continue
            if row[1] != "builder" or row[2] != "installed":
                problems.append(f"roster: {ident} is a registry department and must be "
                                f"'builder installed', found '{row[1]} {row[2]}'")
            if d["reviewer_class"] and f"{ident}-review" not in roster:
                problems.append(f"roster: {ident} is reviewer-class but has no '{ident}-review' reviewer row")
        for ident in sorted(by_id):
            if not os.path.exists(f".claude/agents/{ident}.md"):
                problems.append(f".claude/agents/{ident}.md is missing for registry department {ident!r}")

    for p in problems:
        print(f"  {p}")
    print(f"catalog: {len(depts)} departments, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
