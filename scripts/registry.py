#!/usr/bin/env python3
"""Load config/departments.json — the one canonical copy of department metadata.

Every generator and validator that needs a department's rank, title, executive, category,
reviewer classification, description, version, or keywords reads it from here. Before this
module existed the same facts lived in four places (build-readme.py's META, a REVIEWER set,
.claude-plugin/marketplace.json, and each plugin manifest) and had already drifted in five
fields by the time the registry was introduced.

Loading is strict on shape: a malformed registry is a hard error at load time, not a value
that flows quietly into a generated document. Cross-file consistency (registry vs plugin
tree vs manifests vs roster) is validate-catalog.py's job, not this module's.
"""
import json
import os

REGISTRY_PATH = "config/departments.json"

_DEPT_FIELDS = {
    "id": str,
    "title": str,
    "executive": str,
    "rank": int,
    "category": str,
    "reviewer_class": bool,
    "description": str,
    "version": str,
    "keywords": list,
}
_MARKETPLACE_FIELDS = {"name": str, "owner": dict, "description": str, "version": str}


class RegistryError(SystemExit):
    """Raised (as an exit) so a broken registry stops a generator instead of shaping output."""


def _fail(msg):
    raise RegistryError(f"registry: {msg} — fix {REGISTRY_PATH}")


def load(path=REGISTRY_PATH):
    """Return {"marketplace": {...}, "departments": [...]} after shape validation.

    Departments come back sorted by rank, so every consumer reports in the same order
    without re-implementing the sort.
    """
    if not os.path.exists(path):
        _fail(f"{path} does not exist")
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except ValueError as e:
            _fail(f"not valid JSON: {e}")

    if not isinstance(data, dict) or set(data) != {"marketplace", "departments"}:
        _fail('top level must be exactly {"marketplace": ..., "departments": [...]}')

    market = data["marketplace"]
    for field, kind in _MARKETPLACE_FIELDS.items():
        if not isinstance(market.get(field), kind):
            _fail(f"marketplace.{field} missing or not {kind.__name__}")

    depts = data["departments"]
    if not isinstance(depts, list) or not depts:
        _fail("departments must be a non-empty list")
    seen_ids, seen_ranks = set(), set()
    for d in depts:
        if not isinstance(d, dict):
            _fail("every department entry must be an object")
        ident = d.get("id", "<missing id>")
        missing = sorted(set(_DEPT_FIELDS) - set(d))
        if missing:
            _fail(f"department {ident!r} is missing field(s): {', '.join(missing)}")
        unknown = sorted(set(d) - set(_DEPT_FIELDS))
        if unknown:
            _fail(f"department {ident!r} has unknown field(s): {', '.join(unknown)}")
        for field, kind in _DEPT_FIELDS.items():
            # bool is an int subclass; an int field holding True must still fail.
            if not isinstance(d[field], kind) or (kind is int and isinstance(d[field], bool)):
                _fail(f"department {ident!r}: {field} must be {kind.__name__}")
        if not all(isinstance(k, str) for k in d["keywords"]):
            _fail(f"department {ident!r}: keywords must all be strings")
        if d["id"] in seen_ids:
            _fail(f"duplicate department id {d['id']!r}")
        if d["rank"] in seen_ranks:
            _fail(f"duplicate rank {d['rank']} on {d['id']!r} — ranks order the docs, ties are ambiguous")
        seen_ids.add(d["id"])
        seen_ranks.add(d["rank"])

    data["departments"] = sorted(depts, key=lambda d: d["rank"])
    return data


def departments(path=REGISTRY_PATH):
    """Just the department list, rank-sorted."""
    return load(path)["departments"]
