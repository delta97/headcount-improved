# Architecture

What the pieces are, how they relate, and which system enforces what. The README says what
Headcount is; this document says why it holds together. For what the architecture could carry
next without being rebuilt, see [EXTENDING-HEADCOUNT.md](EXTENDING-HEADCOUNT.md).

## Runtime concepts

**Marketplace.** `.claude-plugin/marketplace.json`, the file Claude Code reads at
`/plugin marketplace add`. It is generated from the canonical registry
(`config/departments.json`) — edit the registry, run `scripts/build-marketplace.py`, and CI
fails if the two disagree.

**Department plugin.** One directory under `plugins/`, independently installable. A project
takes only the functions it needs; installing `finance` does not load a word of `marketing`.
This is the answer to the founding problem: every skill description loads into context, so an
undivided catalog taxes every conversation with all 143.

**Skill.** One directory holding a `SKILL.md`: frontmatter (`name`, `description`) plus a body.
The description is production logic — it is the only part read when deciding whether the skill
loads — and the body is what the model gets once it does. Skills are addressed as
`department:skill`, and uniqueness is enforced per department, not globally: the namespace is
the department (D32).

**Department agent.** One charter per department in `.claude/agents/`, so a department can be
delegated to as a subagent with its own exclusive write surface.

**Builder and reviewer.** The two agent classes in the surface map. A builder edits inside
exactly one exclusive surface. A reviewer is structurally read-only — it holds no write
surface at all, and `agent-guard` fails if one claims any. `security-review` and
`legal-risk-review` review what other departments build, and their blocking findings are not
overrulable by the department under review (D13).

**Orchestrator.** Neither class. It owns no surface, spans surfaces legitimately, and is the
sole committer. Authorship information — which agent produced which hunk — exists only before
the orchestrator commits, which is why `agent-guard diff` runs at that moment and not later.

**Write surface.** The exclusive path globs a builder may touch, declared in
[AGENT-SURFACES.md](AGENT-SURFACES.md). Departments split by surface, not by topic, because a
topic split has no checkable boundary. The map also carries an authority column — whether a
result may land without a human decision (D31).

**Routing.** The behavior that makes the catalog useful: given a natural-language request,
the right skill activates. Routing runs entirely on skill descriptions, which is why
description edits are treated like code changes and why the eval suite exists.

**Evaluation.** `evals/routing/` — prompts with expected, acceptable, and forbidden skills.
The deterministic half runs on every PR; the live half runs a real model when credentials are
supplied. See [../evals/README.md](../evals/README.md).

## Two control planes

Headcount runs two complementary enforcement systems, and the distinction is the most useful
thing on this page:

> A valid skill is not necessarily a useful skill. Structural validation proves it can exist;
> behavioral evaluation measures whether the model uses it correctly.

### The static control plane

Everything `./scripts/check-all.sh` runs — locally and in CI, same entry point, so the two
cannot drift. It guarantees:

- **Valid structure.** Frontmatter parses under the narrow supported subset; names match
  directories; descriptions are substantial.
- **Valid manifests.** Plugin manifests carry the required fields with the required types, and
  agree with the registry field for field.
- **Ownership boundaries.** Every tracked path has exactly one owner; reviewers hold no
  surface; roster, charters, and authority stay coherent.
- **Metadata consistency.** One canonical registry; the marketplace, README, org chart, and
  badge counts are generated from it and staleness fails the build.
- **Resolvable references.** Every `department:skill` mentioned in prose exists; every eval
  case points at an installed skill.

The static plane is cheap, deterministic, and complete over what it covers. Its limit is that
it cannot see behavior: a skill can pass every check above and still never trigger, or trigger
on requests it cannot help.

### The behavioral control plane

`evals/routing/` and its two runners. It measures:

- **Correct selection.** Does the expected skill activate for a realistic phrasing of its
  problem?
- **Reduced overlap.** Near-neighbor cases pin boundaries — the CRO teardown goes to
  demand-generation, the onboarding usability review goes to product — and a forbidden
  selection fails the case.
- **Regression tracking.** Cases are stable by id; a description edit that moves a boundary
  shows up as moved cases, not as a vague feeling.
- **Measurable quality.** The live runner reports pass rate, per-skill precision and recall,
  and confusion pairs — the numbers that tell you *which* description to fix next.

The behavioral plane is sampled rather than complete, and the live half costs API calls, which
is why it is opt-in. The coverage ratchet (`evals/routing/uncovered.txt`) keeps the sampling
honest: a skill without a case must say so in a file that only shrinks knowingly.

### Why both

Each plane catches what the other cannot. The static plane found a marketplace that disagreed
with the plugin manifests in five fields; no amount of routing evaluation would have noticed.
The behavioral plane found a README example routing a generic design review to
`security:threat-modeling`; every structural check passed while it was wrong. Rules that can
be executed live in the static plane. Judgments about behavior live in the behavioral plane.
Prose conventions are what remains when neither is possible, and this repository treats them
as the last resort.

## Where things live

```
config/departments.json        canonical department metadata — the one copy
.claude-plugin/                marketplace, generated from the registry
plugins/<department>/          skills and manifest, the department's exclusive surface
.claude/agents/                one charter per department
docs/AGENT-SURFACES.md         write surfaces, roster, authority — enforced by agent-guard
docs/DECISION-LOG.md           numbered decisions; numbers are addresses and never reused
evals/routing/                 behavioral fixtures and the coverage ratchet
scripts/                       validators and generators; check-all.sh is the entry point
tests/                         unit tests for the scripts themselves, on broken fixtures
```
