#!/usr/bin/env python3
"""Regenerate .claude-plugin/marketplace.json from config/departments.json.

The marketplace file is what Claude Code reads at install time, so it must exist as a real
file — but its content is a pure function of the registry, and before it was generated it
had drifted from the plugin manifests in five fields without any check noticing. Generation
plus a --check in CI makes that class of drift structurally impossible: edit the registry,
run this, and the marketplace cannot disagree with it.

  python3 scripts/build-marketplace.py           regenerate
  python3 scripts/build-marketplace.py --check   fail if stale (CI)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry

OUT = ".claude-plugin/marketplace.json"


def render():
    data = registry.load()
    market = data["marketplace"]
    plugins = []
    for d in data["departments"]:
        plugins.append({
            "name": d["id"],
            "source": f"./plugins/{d['id']}",
            "description": d["description"],
            "version": d["version"],
            "author": {"name": market["owner"]["name"]},
            "keywords": d["keywords"],
            "category": d["category"],
        })
    doc = {
        "name": market["name"],
        "owner": market["owner"],
        "metadata": {
            "description": market["description"],
            "version": market["version"],
        },
        "plugins": plugins,
    }
    return json.dumps(doc, indent=2) + "\n"


def main():
    content = render()
    if "--check" in sys.argv:
        current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if current != content:
            print(f"  {OUT} is stale — run: python3 scripts/build-marketplace.py")
            return 1
        print("marketplace is current")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"{OUT} regenerated — {len(registry.departments())} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
