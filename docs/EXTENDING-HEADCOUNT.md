# What this architecture can support next

None of the following exists yet. This page is here so that the difference between "built" and
"buildable" stays explicit — the repository's documentation must never claim a capability it
does not have, and this is the one place futures are allowed to live. Each section says what
the extension would be, why the current architecture already carries its weight, and what it
would take.

The reason these are credible rather than wishful: departments are independently installable
plugins with exclusive write surfaces, department metadata has one canonical machine-readable
source (`config/departments.json`), skills have stable `department:skill` addresses, and
routing quality is measurable (`evals/routing/`). Most of the extensions below are new
consumers of those four properties, not new machinery.

## Multi-agent workflow recipes

[USE-CASES.md](USE-CASES.md) already works cross-department situations end to end — a SOC 2
demand, an incident, a stalled funnel — as prose. The same pattern can become machine-readable:

```
workflows/
  security-review.json
  product-launch.json
  incident-response.json
```

A recipe would declare the initiating department, participating agents, required reviewers,
handoff order, which stages parallelize, required artifacts, and exit conditions. The surface
map already answers who may write where; a recipe adds *in what order*. Not built because a
workflow engine is heavy and the prose use cases carry the need today; the path is documented
so that if one is built, it consumes the registry rather than inventing a second roster.

## Policy-based reviewer gates

Reviewer-class agents are structurally read-only and not overrulable today (D13); what is
manual is *when* they engage. That decision can become policy: security review required for
authentication changes, legal-privacy review for personal-data handling, finance review above
a spending threshold, brand review for public launch assets. Selection could key on repository
paths (the surface map already parses), task metadata, or workflow declarations. The invariant
to preserve is the one `agent-guard` enforces now: a gate that cannot be checked is a
suggestion.

## Dynamic team composition

Because departments install independently, an orchestrator could assemble a temporary team per
task instead of loading the full organization. "Launch a paid onboarding experiment" composes
`product`, `demand-generation`, `data-analytics`, and `security-review`; nothing else loads.
The plugin boundaries make this possible today by hand; making it automatic needs a
capability directory (next section) and little else.

## Capability discovery

The org chart is generated for humans. The same tree walk can emit a machine-readable
directory:

```
dist/capabilities.json
dist/capabilities.md
```

Each skill exposing its canonical address, department, description, example requests (the
routing eval cases are exactly this), exclusions, related skills, and review requirements.
That lets other harnesses and orchestrators discover Headcount programmatically instead of
parsing markdown.

## Cross-harness support

The skill corpus and department taxonomy are not Claude-specific; the packaging is. The first
adapter exists (D37): `scripts/package/` flattens the canonical tree into a Codex/Agent-Skills
package under `dist/` (gitignored — packages are derived artifacts, never committed), and
`scripts/install/` plus `platforms/codex/` install it safely into a target. Further adapters
would follow the same shape — a builder that consumes `config/departments.json` and the
canonical skill directories, a validator that proves the package matches the source, and the
shared installer core:

```
scripts/package/   builders + package validator (codex today)
scripts/install/   one install engine, CLI on top
platforms/codex/   GUI wrapper and user documentation
```

No drop-in *routing* quality is claimed for any non-Claude harness. An adapter is a real
translation — frontmatter conventions, description length budgets, and routing behavior all
differ per harness — and the routing evals would need to run per target to mean anything
there. Claude Code remains the reference implementation.

## Skill quality scoring

The live routing evals already produce per-skill precision, recall, and confusion pairs. Those
can roll up into standing quality signals — trigger precision, ambiguity rate, description
overlap, stale or uncovered skills, evaluation coverage — and the interactive org chart could
display them:

```
ux-product-auditor
Routing coverage: 92%
Confusion risk: low
Closest neighbor: landing-page-cro-expert
```

Not built because scores without defined criteria are decoration; the criteria come first, and
they come from accumulated eval runs that do not exist yet.

## Versioned skill contracts

Skills could carry contract metadata — `version`, `stability`, `replaces` — making
deprecation, migration, and downstream automation safe. The frontmatter parser deliberately
rejects unknown keys today, which is the right default; adding a key is a one-line change to
the allowed set *plus* a decision-log entry saying what the key promises. The registry already
versions departments; this would extend the same discipline one level down.

## Generated install profiles

Sixteen departments is a real choice burden for a new user. Curated profiles could expand into
known department sets:

```
saas-product:  executive, technology, product, demand-generation, data-analytics, security
go-to-market:  marketing, demand-generation, revenue, customer-experience
```

A profile is a named list of registry ids — trivially validatable by the existing catalog
check, and trivially wrong to hand-maintain anywhere else.

## Organization-specific overlays

A company could keep this repository generic and maintain a private overlay of its own
policies, terminology, systems, escalation paths, architecture standards, and approval rules,
adapting core skills without forking them. This is an architectural use case, not an isolation
or security guarantee — an overlay sees everything the core sees. The D7/D8 vertical-variant
decisions describe the adjacent problem and chose a generator; an overlay model would need its
own decision entry rather than inheriting that one.

## Evidence and provenance-aware skills

Skill metadata could declare epistemics: whether web research is expected, whether primary
sources are required, whether outputs need citations, which claims need qualified professional
review. Most valuable exactly where CONTRIBUTING already draws the regulated-ground line —
legal, finance, security, medical-adjacent, market research — because those are the skills
whose confident wrongness costs the most. Like versioned contracts, this is an allowed-key
extension plus discipline, not new machinery.

---

If you build one of these, the order of operations is the repository's standing one: decision
log entry first (numbers are addresses), executable validation with the feature, documentation
that stops calling it future.
