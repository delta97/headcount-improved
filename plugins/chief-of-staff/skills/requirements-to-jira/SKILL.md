---
name: requirements-to-jira
description: Decomposes a requirements document or a todo line into a Jira epic with its full ticket tree — user stories, subtasks, assignees, and sprint placement — ready to create in the AIP, PMP, QMP, or HSR projects. Use this to break a Notion or Confluence requirements doc into tickets, turn "create an epic for X and break out subtickets" into the actual structure, or draft the story set for an MVP scope. For creating a single ticket, the owner's Jira ticket conventions apply directly; for the delivery plan and schedule around the tickets, prefer `pmo:project-delivery`.
---

# Requirements to Jira

## The failure this prevents

The pattern in the notes is always the same shape — "create epic for the email alerts
ingestion… break out subtickets for Siddhartha," "create Jira ticket in AIP, assign to
Shannon, put in sprint 335" — and it is executed by hand, ticket by ticket, from a
requirements doc that already contains the structure. Hand decomposition drops the
non-obvious tickets: the data validation, the rollback path, the documentation, the
measurement.

## Inputs

A requirements source (a Confluence requirements doc, a Notion PRD, or a meeting decision
with enough substance) plus the routing facts: project (AIP, PMP, QMP, HSR), assignee(s),
sprint or backlog, and any parent initiative to link.

## Method

1. **Read the whole source first.** Note the MVP boundary if one is drawn — tickets must not
   cross it silently; out-of-MVP work becomes labeled backlog stories, not sprint work.
2. **One epic per deliverable outcome**, named for the outcome, not the technology, carrying
   a summary that links back to the source document — the doc stays the requirement of
   record, the epic does not fork it.
3. **Stories from requirement lines**, each in the user-story form the requirement implies,
   with acceptance criteria lifted from the doc's own language wherever it is testable as
   written. A requirement too vague to yield acceptance criteria goes on the questions list,
   not into a vague ticket.
4. **Add the standard invisible tickets** and mark them as additions for review: data
   validation/QA, monitoring or alerting on the new path, documentation, and the
   measurement/reporting the KPI claim needs. The owner deletes what does not apply — better
   to delete than to discover.
5. **Assign and place**: named assignees where the source names them; sprint only for work
   that fits the sprint's remaining capacity, backlog otherwise. Never guess an assignee —
   an unassigned ticket is honest, a misassigned one is noise in someone's queue.
6. **Present the tree as a draft** — epic, stories, subtasks, assignees, sprint — for
   approval before any ticket is created. Creation follows the owner's established Jira
   conventions (project keys, custom fields, and known API pitfalls).

## Rules

- Every ticket traces to a line in the source or is flagged as an addition. No orphan scope.
- Ticket titles are outcomes ("Alert on geo-coverage gaps per network") not tasks ("Update
  the alerts service").
- After creation, write the epic key back into the source document so the doc and the board
  point at each other.
