#!/usr/bin/env python3
"""Validate every SKILL.md's frontmatter: shape, naming, and namespace uniqueness.

Uniqueness is enforced on (department, skill), not on the bare skill name. Claude Code
addresses plugin skills as `department:skill` — that is the whole point of the namespace —
so `finance:forecasting` and `operations:forecasting` can coexist. The earlier global
bare-name check contradicted the documented namespace model (see D32); a cross-department
bare-name collision is now reported as a note for the curator to weigh, never a failure.

The frontmatter parser is deliberately narrow rather than pretending to be YAML. What this
repository supports is exactly:

    ---
    name: lowercase-hyphen-name
    description: a single-line description
    ---

Anything else — unknown keys, multi-line or folded values, lists — is rejected with the
reason, because a construct that a regex silently mis-reads is worse than one that fails.
"""
import glob, os, re, sys, collections

KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
REQUIRED = ("name", "description")
ALLOWED = {"name", "description"}


def parse_frontmatter(text):
    """Return (fields, errors) for the narrow frontmatter subset this repository allows."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        return None, ["no frontmatter"]
    fields, errors = {}, []
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0] in " \t":
            errors.append(f"indented continuation line {raw.strip()!r} — "
                          "frontmatter values must be single-line")
            continue
        kv = KEY_LINE.match(raw)
        if not kv:
            errors.append(f"cannot parse frontmatter line {raw!r}")
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if key not in ALLOWED:
            errors.append(f"unsupported frontmatter key {key!r} — only "
                          + ", ".join(sorted(ALLOWED)) + " are supported")
            continue
        if value in ("", ">", "|") or value.startswith((">", "|")):
            errors.append(f"{key}: multi-line/folded values are not supported — "
                          "write the value on one line")
            continue
        if key in fields:
            errors.append(f"duplicate frontmatter key {key!r}")
            continue
        fields[key] = value
    for key in REQUIRED:
        if key not in fields and not any(key in e for e in errors):
            errors.append(f"missing {key}")
    return fields, errors


def main():
    problems = []
    by_bare_name = collections.defaultdict(list)
    namespaced = collections.defaultdict(list)
    checked = 0
    for path in sorted(glob.glob("plugins/*/skills/*/SKILL.md")):
        checked += 1
        department = path.split(os.sep)[1]
        directory = os.path.basename(os.path.dirname(path))
        fields, errors = parse_frontmatter(open(path, encoding="utf-8").read())
        for e in errors:
            problems.append(f"{path}: {e}")
        if fields is None or "name" not in fields:
            continue
        name = fields["name"]
        if name != directory:
            problems.append(f"{path}: name {name!r} != directory {directory!r}")
        if not SLUG.fullmatch(name):
            problems.append(f"{path}: {name!r} is not lowercase-hyphenated")
        desc = fields.get("description", "")
        if desc and len(desc) < 80:
            problems.append(f"{path}: description too thin to trigger reliably")
        by_bare_name[name].append(f"{department}:{name}")
        namespaced[(department, name)].append(path)

    # (department, skill) is the address Claude Code resolves; a duplicate address is a failure.
    for (department, name), paths in sorted(namespaced.items()):
        if len(paths) > 1:
            problems.append(f"duplicate skill {department}:{name} — {', '.join(paths)}")

    # A bare-name collision across departments is legal under the namespace model but worth a
    # human look: two skills answering to the same short name can still confuse a reader.
    for name, addrs in sorted(by_bare_name.items()):
        if len(addrs) > 1:
            print(f"  note: {name!r} exists in more than one department ({', '.join(sorted(addrs))}) "
                  "— fine for routing, worth checking the descriptions do not overlap")

    for problem in problems:
        print(f"  {problem}")
    print(f"{checked} skills checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
