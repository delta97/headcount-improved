#!/usr/bin/env python3
"""Deterministic validation of the routing evaluation fixtures in evals/routing/.

This is the static half of the behavioral control plane: it cannot tell whether the model
routes a prompt correctly (scripts/run-routing-evals.py does that, with credentials), but it
can prove the fixtures themselves are sound — every referenced skill exists, no case both
requires and forbids the same skill, and every installed skill is either covered by at least
one positive case or explicitly listed as uncovered. That last rule is a ratchet: adding a
skill without either an eval case or an exemption line fails CI, so coverage can only be
grown or knowingly declined, never silently skipped.

Runs on every PR with no network and no credentials.
"""
import glob
import json
import os
import re
import sys

CASES = "evals/routing/cases.jsonl"
EXEMPTIONS = "evals/routing/uncovered.txt"
REQUIRED_FIELDS = {"id": str, "prompt": str, "expected": list, "acceptable": list,
                   "forbidden": list, "tags": list}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REF_RE = re.compile(r"^([a-z0-9]+(?:-[a-z0-9]+)*):([a-z0-9]+(?:-[a-z0-9]+)*)$")


def installed_skills():
    out = set()
    for path in glob.glob("plugins/*/skills/*/SKILL.md"):
        parts = path.split(os.sep)
        out.add(f"{parts[1]}:{parts[3]}")
    return out


def load_cases(problems):
    if not os.path.exists(CASES):
        problems.append(f"{CASES} does not exist")
        return []
    cases = []
    for n, line in enumerate(open(CASES, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except ValueError as e:
            problems.append(f"{CASES}:{n}: not valid JSON: {e}")
            continue
        if not isinstance(case, dict):
            problems.append(f"{CASES}:{n}: each line must be a JSON object")
            continue
        case["_line"] = n
        cases.append(case)
    return cases


def main():
    problems = []
    skills = installed_skills()
    cases = load_cases(problems)

    seen_ids = set()
    covered = set()
    for case in cases:
        n = case.pop("_line")
        where = f"{CASES}:{n}"
        missing = sorted(set(REQUIRED_FIELDS) - set(case))
        if missing:
            problems.append(f"{where}: missing field(s): {', '.join(missing)}")
            continue
        unknown = sorted(set(case) - set(REQUIRED_FIELDS))
        if unknown:
            problems.append(f"{where}: unknown field(s): {', '.join(unknown)}")
        bad_type = [f for f, kind in REQUIRED_FIELDS.items() if not isinstance(case[f], kind)]
        if bad_type:
            problems.append(f"{where}: wrong type for: {', '.join(bad_type)}")
            continue

        cid = case["id"]
        where = f"{CASES}:{n} ({cid})"
        if not ID_RE.fullmatch(cid):
            problems.append(f"{where}: id is not lowercase-hyphenated")
        if cid in seen_ids:
            problems.append(f"{where}: duplicate case id")
        seen_ids.add(cid)

        if len(case["prompt"].strip()) < 15:
            problems.append(f"{where}: prompt too short to be a realistic request")

        expected, acceptable, forbidden = case["expected"], case["acceptable"], case["forbidden"]
        for field in ("expected", "acceptable", "forbidden"):
            for ref in case[field]:
                if not isinstance(ref, str) or not REF_RE.fullmatch(ref):
                    problems.append(f"{where}: {field} entry {ref!r} is not department:skill")
                elif ref not in skills:
                    problems.append(f"{where}: {field} names {ref!r}, which is not an installed skill")
        for a, b in (("expected", "acceptable"), ("expected", "forbidden"),
                     ("acceptable", "forbidden")):
            both = sorted(set(case[a]) & set(case[b]))
            if both:
                problems.append(f"{where}: {', '.join(both)} in both {a} and {b}")
        if not (expected or acceptable or forbidden):
            problems.append(f"{where}: asserts nothing — expected, acceptable and forbidden all empty")
        for tag in case["tags"]:
            if not isinstance(tag, str) or not ID_RE.fullmatch(tag):
                problems.append(f"{where}: tag {tag!r} is not lowercase-hyphenated")

        covered.update(set(expected) | set(acceptable))

    # ── Coverage ratchet ─────────────────────────────────────────────────────────
    exempt = set()
    if os.path.exists(EXEMPTIONS):
        for n, line in enumerate(open(EXEMPTIONS, encoding="utf-8"), 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if not REF_RE.fullmatch(line):
                problems.append(f"{EXEMPTIONS}:{n}: {line!r} is not department:skill")
                continue
            if line not in skills:
                problems.append(f"{EXEMPTIONS}:{n}: {line!r} is not an installed skill — remove the stale line")
            if line in exempt:
                problems.append(f"{EXEMPTIONS}:{n}: {line!r} listed twice")
            exempt.add(line)

    for skill in sorted(skills - covered - exempt):
        problems.append(f"{skill} has no positive routing case and is not listed in {EXEMPTIONS}")
    for skill in sorted(covered & exempt):
        problems.append(f"{skill} is covered by a case but still listed in {EXEMPTIONS} — remove the line")

    for p in problems:
        print(f"  {p}")
    print(f"routing evals: {len(cases)} cases, {len(covered & skills)}/{len(skills)} skills covered, "
          f"{len(exempt - covered)} exempted, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
