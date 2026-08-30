---
name: ai-portfolio-tracker
description: Builds and operates the AI initiative portfolio database — intake scoring, Value and TCO ordering, decision statuses, WIP limits — and generates the recurring portfolio review and KPI/spend/risk documents from it. Use this to stand up or update the AI portfolio tracker, score a new AI request against the intake rubric, prepare the biweekly portfolio review or monthly KPI review, or answer what is in the pipeline and why it is ordered that way. For writing the governance process itself as a document, use `exec-position-paper`; for enterprise-wide risk frameworks, prefer `legal-risk:enterprise-risk`.
---

# AI portfolio tracker

## The gap this closes

The governance design exists — a written intake, prioritization, and graduation process with a
weighted value scorecard, TCO sizing, Value-over-TCO ordering, decision statuses, WIP limits,
and a review cadence — but no database implements it. Initiatives are tracked as prose
headings, so the ordering the process prescribes is recomputed in heads, differently each
time. This skill makes the spec operational and keeps it that way.

## The source of truth

**The canonical process document — "AI Request Intake, Prioritization & Graduation Process" —
governs, not this file.** Read it before building or scoring anything: the exact scorecard
criteria and weights, the TCO scale, the status vocabulary, and the cadence live there and are
the owner's to change. If this skill's summary and that document ever disagree, the document
is right — update the practice, not the doc.

The spec's shape, for orientation: a federated tiered model (Build → Share → Validate →
Graduate); a 100-point weighted value scorecard; a small-integer TCO sizing scale; default
ordering by Value ÷ TCO; seven decision statuses from Self-Service through Retired; per-
department force-ranked backlogs; WIP limits; and a biweekly portfolio review / monthly KPI,
spend and risk review / quarterly capacity rebalance cadence.

## Building or repairing the database

1. Derive the schema from the process doc: one row per initiative; properties for department,
   requester, each scorecard criterion, computed value score, TCO, Value÷TCO, decision
   status, owner, WIP flag, and dates (requested, decided, last reviewed).
2. Seed it from what exists: the initiative ideas page, active Jira epics, and initiatives
   named in recent meeting notes. Every seeded row gets a status honestly — most start as
   Needs Evidence, not Approved.
3. Build three views: the force-ranked backlog (by Value÷TCO within department), the active
   board (by status, WIP-limited columns), and the review queue (last-reviewed older than the
   cadence).

## Scoring a new request

Score each criterion from evidence in the request, showing the arithmetic; a criterion with no
evidence scores low and says so — the scorecard exists to make "we have no evidence" visible,
not to be talked up. Present the score, TCO, and resulting rank *as a draft for the owner*:
the rubric is decision support, and the portfolio council decides.

## Generating the review documents

- **Biweekly portfolio review:** ranked backlog with movement since last review, status
  changes, WIP-limit state, and the two or three ordering decisions that need the council.
- **Monthly KPI/spend/risk review:** per active initiative — the KPI it claimed, the number
  now, spend against sizing, and risks with triggers. An initiative that cannot state its
  number is itself a finding.

## Rules

- Never change a decision status without a decision to cite. The tracker records governance;
  it does not perform it.
- A row untouched for two cadences is flagged, not deleted — stale is information.
