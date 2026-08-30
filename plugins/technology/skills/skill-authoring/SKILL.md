---
name: skill-authoring
description: Writes and revises agent skills so they trigger at the right moments and give usable instruction when they do. Use this when creating a new skill, editing an existing one, diagnosing a skill that fires too often or never fires, or reviewing a set of skills for overlap. Also use before adding to a skill library, to check the capability is not already covered.
---

# Skill authoring

A skill is judged twice: on whether it loads at the right moment, and on whether it helps once
loaded. Most fail the first test.

## The description does the triggering

It is the only part read when deciding whether to load. Write it for that job:

- Lead with **what the skill does**, in one clause.
- Then **when to reach for it** — the situations, in the words someone would actually use, including
  the oblique ones ("why isn't this converting" as well as "CRO audit").
- Name the **edge cases that should still trigger it**, and where useful, what should *not*.

Vague descriptions produce two failures at once: the skill misses cases it should catch, and fires
on cases it cannot help.

## The body does the work

Write for someone competent who has not thought about this problem today. That means:

- **Method over exhortation.** "Be thorough" is noise. An ordered procedure is instruction.
- **State the failure behind each rule.** A rule with no failure attached gets optimized away by the
  next reader.
- **Be specific enough to be wrong.** Guidance too hedged to contradict is too vague to follow.
- **Put long material in `references/`** and say when to read it. The body should fit in working
  memory.

## Overlap is the silent killer

Two skills whose descriptions both match a request means neither reliably wins. Before adding one,
check what already covers the ground. Prefer extending an existing skill, or consolidating the
family into one skill with references, over adding a near-neighbor.

## Mechanics

- `name` must be lowercase-hyphenated and equal the directory name, or the skill will not load.
- One skill, one directory, `SKILL.md` at its root; supporting material in `references/` and
  `scripts/`.

## State the boundary in the description

Where a skill has a near-neighbor — another skill a reasonable request could also match — say
which requests belong to the neighbor, in the description itself, by address: "Prefer
`demand-generation:landing-page-cro-expert` when the subject is a marketing landing page."
The description is the only thing routing reads, so a boundary stated anywhere else does not
exist at the moment it matters.

## Verify before shipping

Write three requests that should trigger it and two that should not, and check the description
actually discriminates. If a near-miss request would pull it in, tighten the description.

Where the skill library has an executable routing eval suite — this repository keeps one in
`evals/routing/` — record those requests as cases instead of discarding them: the ones that
should trigger as `expected`, the near-misses as cases for the neighbor with this skill in
`forbidden`. A judgment written down once becomes a regression test; a judgment made in your
head is remade, differently, by the next editor.
