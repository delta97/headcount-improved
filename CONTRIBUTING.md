# Contributing

Contributions are welcome. This document covers the license, the bar for a skill, and the checks.

## License

**By submitting a contribution you agree it is licensed under the [MIT License](LICENSE), the same
terms as the rest of this repository.**

Contribute only work you have the right to license this way. In particular, do not paste in skills,
prose, or reference material from another project unless you wrote it or its license permits
relocation — and if it does, say so in the pull request. Every line in this repository is original
to it.

`scripts/check-provenance.py` is a backstop, not a proof. It scans every text file in the tree for
license headers, copyright notices, and SPDX identifiers, flags files named like licenses
(`LICENSE`, `COPYING`, `NOTICE`, `PATENTS`, `AUTHORS`), and rejects bundled font assets. It cannot
detect prose lifted without a notice attached — which is the case that matters most. Review is what
catches that; the check only catches the obvious.

## What makes a good skill

A skill is judged twice: whether it loads at the right moment, and whether it helps once loaded.

**The description does the triggering.** It is the only part read when deciding whether to load. Lead
with what the skill does, then when to reach for it — in the words someone would actually use,
including the oblique ones. Vague descriptions fail twice over: they miss cases they should catch
and fire on cases they cannot help.

**The body does the work.** Write for someone competent who has not thought about this problem
today:

- **Method over exhortation.** "Be thorough" is noise; an ordered procedure is instruction.
- **State the failure behind each rule.** A rule with no failure attached gets optimized away by the
  next reader.
- **Be specific enough to be wrong.** Guidance too hedged to contradict is too vague to follow.
- **Long material goes in `references/`**, with the body saying when to read it.

**Where a skill touches regulated ground** — law, privacy, compensation, medical, financial, or
safety advice — say plainly what it structures and what needs qualified professional input. Skills
that sound authoritative and are subtly wrong in these areas cause real harm, because they get
trusted.

Read `technology:skill-authoring` for the full treatment, and `executive:agent-hierarchy` for why
departments are split by exclusive write surface rather than by topic.

## Before opening a pull request

```
./scripts/check-all.sh
```

The checks, the same ones CI runs. (A test in `tests/test_docs_current.py` fails the build if
this table and `check-all.sh` disagree, so the list below is the executed list.)

| Check | What it enforces |
|---|---|
| Surface map is coherent | Every tracked path has exactly one owner; roster, charters, and authority agree |
| Unit tests (Node) | `agent-guard.mjs` glob, parsing, check, and diff behavior against broken-map fixtures |
| Unit tests (Python) | Validators and generators against edge-case fixtures, plus these doc-drift guards |
| Skill frontmatter is valid | `name` equals the directory name, lowercase-hyphenated, unique per department, description substantial, only supported frontmatter |
| Catalog is consistent | `config/departments.json` agrees with the plugin tree, every manifest, the roster, and the charters |
| Marketplace is current | `.claude-plugin/marketplace.json` matches regeneration from the registry |
| No third-party license text | No license headers, copyright notices, license-named files, or font assets |
| README is current | README and org-chart tables match regeneration from the tree |
| Social card is current | The social card matches regeneration |
| Org chart is current | The interactive org chart matches regeneration |
| Routing eval fixtures are valid | Every eval case resolves, coverage is complete or explicitly declined |
| Codex package builds and validates | The flattened runtime package derives cleanly from the canonical tree and matches it file for file (D37) |
| Skill references resolve | Every `department:skill` mentioned in the docs exists |
| US English spelling | House style — no British spellings |
| Manifests parse | Marketplace and plugin manifests are valid JSON |

**Stage your files first.** The surface guard reads `git ls-files`, so an unstaged file is invisible
to it — the check will pass and then fail once committed. The script warns when untracked files are
present.

## Adding a skill

1. `plugins/<department>/skills/<skill-name>/SKILL.md`
2. Frontmatter `name` must equal the directory name. Skills are addressed as `department:skill`,
   so a name only has to be unique within its department — but check the note the validator
   prints if the bare name already exists elsewhere, and make sure the two descriptions cannot
   match the same request.
3. Check nothing already covers the ground. Two skills whose descriptions both match a request means
   neither reliably wins — prefer extending an existing skill, or folding a family into one skill
   with references, over adding a near-neighbor.
4. Add at least one positive routing case to `evals/routing/cases.jsonl` — a request, phrased the
   way someone would actually ask it, that should load the skill. If the skill has a near-neighbor,
   add a case that should load the neighbor with your skill in `forbidden`. If you genuinely cannot
   write a case yet, add the skill to `evals/routing/uncovered.txt` — the check fails if you do
   neither, and that is deliberate.

## House style

**US English.** The author writes in US English and the catalog does too — *license*, *program*,
*catalog*, *behavior*, *prioritize*, *center*. `scripts/check-us-english.py` fails the build on
British spellings and `--fix` rewrites them.

The list is of exact word forms, not stems, because stems are a trap here: *analysis*, *analyst*,
*specialist* and *realistic* are already correct US English and must never be rewritten.

## Adding a department

All five, in the same change, or the check fails:

1. `plugins/<name>/skills/` and `plugins/<name>/.claude-plugin/plugin.json`
2. An entry in `config/departments.json` — the canonical registry: rank, title, executive,
   category, reviewer classification, description, version, keywords. The manifest in step 1 must
   carry the same description, version, and keywords, or `validate-catalog.py` fails.
3. A roster row and a `surface:` block in `docs/AGENT-SURFACES.md`
4. A charter at `.claude/agents/<name>.md`
5. Regenerate the derived files: `python3 scripts/build-marketplace.py` (the marketplace is
   generated from the registry — never edit `.claude-plugin/marketplace.json` by hand),
   `python3 scripts/build-readme.py`, and a glyph in `scripts/build-org-chart.py` followed by
   `python3 scripts/build-org-chart.py`.

The generators read the registry and cross-check it against the plugin tree, refusing to run while
the two disagree, so a new department cannot end up missing from the README, the org chart, or the
marketplace while the checks still pass.

Give it a chief before any specialists — the department's remit should exist before things are added
to it.

## Adding a file outside `plugins/`

It needs an owner in `docs/AGENT-SURFACES.md`, or the surface check fails. Most such files belong to
`repo-meta`.

## Decisions

Choices with more than one defensible answer go in `docs/DECISION-LOG.md`, numbered. A number is
assigned when the question is raised, not when it is answered, and is never reused. Every entry
carries lettered options and an explicit recommendation.
