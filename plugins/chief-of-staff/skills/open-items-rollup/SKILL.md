---
name: open-items-rollup
description: Regenerates the consolidated open-items page from the weekly Notion notes pages — sweeping unchecked todos, grouping them by workstream, tiering by urgency, and flagging how long each has been open. Use this to roll up outstanding action items, consolidate todos scattered across weekly pages, rebuild the "Outstanding Action Items" page, triage what is overdue, or answer "what is still open." For delivering a bounded project rather than tracking personal open items, prefer `pmo:project-delivery`.
---

# Open-items rollup

## The failure this prevents

The hand-built version of this rollup worked — five urgency tiers, carry-forward provenance,
owner sections — and then died of its own maintenance cost: built once on June 22, never
regenerated, while items like "Asana hours sync" sat open for six weeks with no index pointing
at them. A rollup that is not regenerated is worse than none, because it reads as current.

## Sources

The weekly notes pages (titled with a date mention plus "Notes and Todo"), newest first, back
to the last rollup or four weeks — whichever is further. Unchecked checkboxes are the unit of
work; the H1 date above each gives its origin date, and the H2 gives its meeting context.

## Method

1. **Sweep.** Collect every unchecked `- [ ]` from the window. Skip empty checkboxes (no
   text) — they are typing artifacts, not work.
2. **Dedupe by intent, not by string.** The same follow-up gets rephrased week to week
   ("follow up with Ryan for the sheet link" / "Ryan — campaign grouping sheet"). Merge them
   and keep the *earliest* origin date; the age is the point.
3. **Group by workstream**, using the established buckets and emoji: ⏰ Deadline-Driven —
   Triage First, 📡 Paid Media, 🤖 AIP, 💼 Chris Pallatroni, 🏠 Gutenberg, 🧭 Org/Process,
   ✈️ Personal. Add a bucket only when several items genuinely fit nothing existing.
4. **Tier within groups**: 🔴 Tier 1 (blocking someone, or deadline inside a week) down to
   ⚪ Tier 5 (someday). An item waiting on another person is at least Tier 2 — the cost of it
   sliding lands on them.
5. **Stamp provenance and age** on every item: "open since 2026-08-11", and "carried from" the
   prior rollup when it appeared there too. An item on its third rollup gets called out at the
   top: it is either not real work (delete it) or it needs to be scheduled, not listed.
6. **Write the page** titled with today's date mention plus "Outstanding Action Items & Open
   Todos", replacing content in place if a page for the cycle exists. Open with a three-line
   summary: total open, count over two weeks old, count blocking others.

## Rules

- Never mark an item done during the sweep. Ambiguity about whether something is finished is a
  question for the owner, listed under its own heading, not a judgment call.
- Personal items stay in the rollup (they are real) but always last — the rollup is read at
  work.
- Keep it one page. The moment it needs a table of contents, the tiers are too generous.
