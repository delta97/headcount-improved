#!/usr/bin/env python3
"""Regenerate README.md and the org-chart department table. Run: python3 scripts/build-readme.py
Verified in CI via --check, so the README can never drift from what the repo actually contains."""
import glob, os, re, json, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Display metadata (rank, title, executive, reviewer classification) comes from the canonical
# registry at config/departments.json — the same source the marketplace is generated from and
# validate-catalog.py checks the plugin manifests against, so the docs cannot disagree with either.
import registry

def load_departments():
    """The registry is cross-checked against the plugin tree before anything is generated. A
    department present on disk but missing from the registry is a hard error rather than a silent
    omission — the same mistake used to drop a department out of both generated docs while
    --check still passed."""
    depts = registry.departments()
    found = {os.path.basename(os.path.dirname(os.path.dirname(m)))
             for m in glob.glob("plugins/*/.claude-plugin/plugin.json")}
    ids = {d["id"] for d in depts}
    missing = sorted(found - ids)
    if missing:
        sys.exit("build-readme: no registry entry for department(s) "
                 + ", ".join(missing)
                 + "\n  add an entry to config/departments.json")
    stale = sorted(ids - found)
    if stale:
        sys.exit("build-readme: registry names department(s) that are not on disk: "
                 + ", ".join(stale)
                 + "\n  remove them from config/departments.json")
    return depts


DEPARTMENTS = load_departments()
ORDER = [(d["id"], d["title"], d["executive"]) for d in DEPARTMENTS]
REVIEWER = {d["id"] for d in DEPARTMENTS if d["reviewer_class"]}


def summarize(path, limit=165):
    text = open(path, encoding="utf-8").read()
    front = re.match(r"^---\s*\n(.*?)\n---", text, re.S).group(1)
    desc = re.search(r"^description:\s*(.*)$", front, re.M).group(1).strip()
    cut = re.split(r"(?:\.\s+)(?:Also )?[Uu]se (?:this|it)\b", desc)[0]
    if len(cut) < 40:
        cut = desc
    cut = cut.rstrip(" .,—-")
    return cut[: limit - 1].rstrip() + "…" if len(cut) > limit else cut


def skills(dept):
    return sorted(glob.glob(f"plugins/{dept}/skills/*/SKILL.md"))


total = sum(len(skills(d)) for d, _, _ in ORDER)
# Badge counts come from the same tree walk as the tables below, so they cannot drift from
# reality — a wrong count fails `build-readme.py --check` in CI like any other staleness.
B = "https://img.shields.io/badge"
out = [
    '<h1 align="center">headcount</h1>',
    "",
    '<p align="center"><b>Add a department, not a prompt.</b></p>',
    "",
    '<p align="center">',
    f'  <a href="https://claude.com/claude-code"><img alt="Built for Claude Code"'
    f' src="{B}/built%20for-Claude%20Code-D97757?style=flat-square"></a>',
    f'  <img alt="{len(ORDER)} departments" src="{B}/departments-{len(ORDER)}-3F4B5B?style=flat-square">',
    f'  <img alt="{total} skills" src="{B}/skills-{total}-3F4B5B?style=flat-square">',
    f'  <a href="LICENSE"><img alt="MIT licensed" src="{B}/license-MIT-3F4B5B?style=flat-square"></a>',
    f'  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="{B}/PRs-welcome-2EA043?style=flat-square"></a>',
    "</p>",
    "",
    # The chart is the clearest single statement of what this is, so it leads. GitHub does not
    # render HTML from a repository, so the image links to the Pages copy, which does.
    '<p align="center">',
    '  <a href="https://cbrock84.github.io/headcount/org-chart.html">',
    "    <picture>",
    '      <source media="(prefers-color-scheme: dark)" srcset="docs/assets/org-chart-dark.png">',
    f'      <img alt="The headcount org chart — {len(ORDER)} departments, {total} skills, searchable"'
    ' src="docs/assets/org-chart-light.png" width="840">',
    "    </picture>",
    "  </a>",
    "</p>",
    "",
    '<p align="center">',
    '  <a href="https://cbrock84.github.io/headcount/org-chart.html"><b>Open the interactive org'
    " chart</b></a> — search every skill, open a department, jump to the source.",
    "</p>",
    "",
    "An agent organization for [Claude Code](https://claude.com/claude-code), structured as a company:",
    f"a chief executive over {len(ORDER)} departments, {total} skills in total.",
    "",
    "Every department is an independently installable plugin, so a project loads only the functions it",
    "needs rather than all of them at once.",
    "",
    "## Install",
    "",
    "```",
    "/plugin marketplace add cbrock84/headcount",
    "/plugin install security@headcount",
    "```",
    "",
    "Install as many departments as the project needs. Skills are addressed as `department:skill` —",
    "`security:threat-modeling`, `finance:unit-economics` — so names never collide.",
    "",
    "## Use",
    "",
    "Skills load themselves when a request matches. Ask a question in the department's territory and the",
    "right specialist engages:",
    "",
    "| You ask | What loads |",
    "|---|---|",
    "| \"why isn't this landing page converting?\" | `demand-generation:landing-page-cro-expert` |",
    "| \"review this design before we build it\" | `security:threat-modeling` |",
    "| \"can we afford this hire?\" | `finance:unit-economics` |",
    "| \"our growth has stalled\" | `executive:business-growth-consultant` |",
    "",
    "Invoke one directly by name when you want a specific lens: `/finance:financial-modeling`.",
    "",
    "Seven situations that cross departments — a SOC 2 demand from an enterprise prospect, a",
    "security incident, a stalled funnel — are worked through end to end in",
    "[docs/USE-CASES.md](docs/USE-CASES.md), including where a reviewer-class department stops the",
    "work rather than adding an opinion.",
    "",
    "Each department also ships an agent charter in `.claude/agents/`, so a department can be delegated",
    "to as a subagent with its own exclusive write surface.",
    "",
    "## Departments",
    "",
]
for dept, title, exec_role in ORDER:
    paths = skills(dept)
    tag = " · **reviewer-class**" if dept in REVIEWER else ""
    out += [f"<details>", f"<summary><b>{title}</b> ({exec_role}) — {len(paths)} skills{tag}</summary>", "",
            "| Skill | What it does |", "|---|---|"]
    for p in paths:
        out.append(f"| `{os.path.basename(os.path.dirname(p))}` | {summarize(p)}. |")
    out += ["", "</details>", ""]

out += [
    "**Reviewer-class departments** (`security`, `legal-risk`) review what other departments build, and",
    "their blocking findings are not overrulable by the department under review. That is why the CISO",
    "and the CLO report to the chief executive rather than into the function they oversee.",
    "",
    "## How it is organized",
    "",
    "```",
    "plugins/<department>/",
    "  .claude-plugin/plugin.json   department manifest",
    "  skills/<skill>/SKILL.md      frontmatter name equals the directory name",
    ".claude/agents/<id>.md         one charter per department",
    "docs/AGENT-SURFACES.md         every path has exactly one owner, enforced in CI",
    "docs/DECISION-LOG.md           numbered decisions with options and recommendations",
    "docs/USE-CASES.md              situations worked end to end across departments",
    "docs/org-chart.html           interactive org chart, searchable across every skill",
    "docs/index.html               GitHub Pages entry point, redirects to the chart",
    "```",
    "",
    "Agents split by **exclusive write surface**, not by topic — a topic split has no checkable",
    "boundary, and two agents working on \"SEO\" and \"UI\" both end up in the same file. See",
    "`executive:agent-hierarchy` for the method.",
    "",
    "## Contributing",
    "",
    "```",
    "./scripts/check-all.sh",
    "```",
    "",
    "Verifies the surface map is coherent, every skill's frontmatter is valid and unique, no",
    "third-party license text has appeared, the generated README and social card are current, every",
    "`department:skill` reference in the docs resolves, spelling is US English, and every manifest",
    "parses. CI runs the same",
    "script, so local and CI cannot drift.",
    "",
    "A new department needs its roster row in `docs/AGENT-SURFACES.md`, a surface block, a charter in",
    "`.claude/agents/`, and an entry in `.claude-plugin/marketplace.json` — all in the same change, or",
    "the check fails.",
    "",
    "## Writing",
    "",
    "Notes from building and running this, and from the day job — technology, security, AI, and the",
    "operating side of all three — go out at [cbrock84.substack.com](https://cbrock84.substack.com).",
    "",
    "The piece on why this is shaped like an org chart at all, and what broke before it was:",
    "[Giving AI agents an org chart]"
    "(https://cbrock84.substack.com/p/giving-ai-agents-an-org-chart).",
    "",
    "## License",
    "",
    "MIT — see [LICENSE](LICENSE). Every skill here was written for this repository.",
    "",
    "Built by [Chris Brock](https://chrisbrock.io).",
    "",
    "---",
    "",
    "<sub>README generated by `scripts/build-readme.py` — edit that, not this file.</sub>",
    "",
]
content = "\n".join(out)

# The org chart's department table drifts the same way the README did. Generate it between
# markers so the two cannot disagree; the analysis prose around it stays hand-written.
chart_rows = "\n".join(
    f"| `{d}` | {t} | {e} | {len(skills(d))}"
    + (" · reviewer-class |" if d in REVIEWER else " |")
    for d, t, e in ORDER
)
chart_block = (
    "<!-- BEGIN GENERATED: departments -->\n"
    f"| Department | Function | Executive | Skills |\n|---|---|---|---|\n{chart_rows}\n"
    f"\n{len(ORDER)} departments, {total} skills.\n"
    "<!-- END GENERATED: departments -->"
)
chart_path = "docs/org-chart.md"
chart_current = open(chart_path, encoding="utf-8").read()
chart_new = re.sub(
    r"<!-- BEGIN GENERATED: departments -->.*?<!-- END GENERATED: departments -->",
    lambda _: chart_block,
    chart_current,
    flags=re.S,
)

if "--check" in sys.argv:
    if chart_current != chart_new:
        print("  docs/org-chart.md department table is stale — run: python3 scripts/build-readme.py")
        sys.exit(1)
    current = open("README.md", encoding="utf-8").read() if os.path.exists("README.md") else ""
    if current != content:
        print("  README.md is stale — run: python3 scripts/build-readme.py")
        sys.exit(1)
    print("README is current")
    sys.exit(0)

open("README.md", "w", encoding="utf-8").write(content)
open(chart_path, "w", encoding="utf-8").write(chart_new)
print(f"README.md and org-chart.md regenerated — {len(ORDER)} departments, {total} skills")
