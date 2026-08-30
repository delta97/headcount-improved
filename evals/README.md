# Evaluations

Structural validation proves a skill *can* load — the frontmatter parses, the name resolves,
the description is substantial. None of that says whether the *right* skill loads when someone
asks a real question, and that selection is the product this repository ships. The routing
evals make it observable and regression-testable instead of a matter of author judgment.

## Layout

```
evals/routing/
  cases.jsonl      one evaluation case per line — see schema.json for the shape
  schema.json      documents the case format; the validator is authoritative
  uncovered.txt    skills with no positive case yet, listed deliberately
```

## The two halves

**Deterministic (every PR, no credentials).** `python3 scripts/validate-routing-evals.py`
proves the fixtures are sound: every referenced skill exists, ids are unique, no case both
requires and forbids the same skill, and every installed skill either has a positive case or
appears in `uncovered.txt`. That file is a ratchet — a covered skill may not stay listed, and
a new skill must arrive with a case or a deliberate exemption line. `check-all.sh` runs this
with everything else.

**Live (opt-in, needs `ANTHROPIC_API_KEY`).** `python3 scripts/run-routing-evals.py` asks a
real model to pick a skill for each case's prompt, given the same material Claude Code routes
on — every skill's name and description. It reports pass rate, per-skill precision and recall,
confusion pairs, and forbidden-selection (false-positive) rate, and can gate on a threshold.
It is not wired into ordinary CI on purpose: pull requests must not require paid API calls or
secrets. Run it locally before and after editing descriptions, or via the manual
`routing-evals` workflow.

```
export ANTHROPIC_API_KEY=...
python3 scripts/run-routing-evals.py --runs 3 --json out.json
python3 scripts/run-routing-evals.py --tags near-neighbor   # just the boundary cases
```

## What a case asserts

- `expected` — the skill(s) that should activate; the first entry is the ideal answer.
- `acceptable` — selections that pass without being ideal. Legitimate ambiguity is recorded
  here rather than forced into a fake single answer.
- `forbidden` — skills that must not activate; selecting one fails the case outright.
- A case with empty `expected` and non-empty `acceptable` is an ambiguity case; one with only
  `forbidden` is a pure negative.

## What the live eval does and does not measure

The runner presents the full catalog of `department:skill` names and descriptions and asks
which single skill should handle the request — the same information Claude Code's own routing
sees, but not the same code path. Treat results as a strong signal about description quality
and boundary overlap, not as a certification of harness behavior. What has proven most useful
is the *delta*: run before and after a description change and watch the confusion pairs move.

## Writing cases

Follow `technology:skill-authoring`: for a new skill, write at least one request that should
trigger it and, where it has a near-neighbor, one that should trigger the neighbor instead —
with the neighbor in `forbidden`. Phrase prompts the way people actually ask ("why isn't this
converting", not "perform a CRO audit"), and add expert phrasings as separate cases. Keep
coverage honest: if you cannot write a triggering request for a skill, that is a finding about
the skill, not a reason to skip the case.
