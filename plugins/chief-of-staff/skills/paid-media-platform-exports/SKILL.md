---
name: paid-media-platform-exports
description: Reformats PMP campaign-targeting exports into each ad platform's required upload format, applying the per-platform quirks that make the manual version error-prone — geo identifier conventions, column names, and file shape. Use this to convert a PMP CSV export for a specific platform, prepare geo or DMA targeting uploads, check an export against a platform's known format rules, or extend the format reference when a platform changes. For deciding the targeting itself rather than formatting it, prefer `demand-generation:paid-advertising`.
---

# Paid-media platform exports

## The failure this prevents

The step between "PMP exports the targeting list" and "the platform accepts the upload" is
manual reformatting, done per platform, described in the owner's own notes as time-consuming
and error-prone. Roughly five platforms each want the same data shaped differently — the
canonical trap being geo identifiers: some platforms take a DMA *code*, others the DMA *name*,
and a file that silently uses the wrong one uploads cleanly and targets wrongly. Wrong
targeting is spend, not a formatting nit.

## The format reference

`references/platform-formats.md` is the memory of this skill: one section per platform, each
recording the geo identifier convention (code vs. name, and the exact naming source), required
columns and their order, header names, file type and encoding, and any row limits or
segmentation rules — with a "verified on" date per section.

**The reference is grown, not assumed.** Where a platform's section is marked unverified,
confirm against the platform's current bulk-upload documentation or a known-good past upload
before producing a file, and record what was confirmed. A guessed format defeats the purpose:
the skill exists because guessing is the current process.

## Method

1. Identify the target platform and the export in hand; read the platform's section of the
   reference. If it is missing or unverified, verify first (above) — never generate from an
   unverified section without saying so.
2. Map columns from the PMP export to the platform's schema. Transform geo identifiers
   explicitly: when converting between DMA code and name, use a single lookup applied to
   every row — never row-by-row judgment.
3. Validate before delivering: row count in equals row count out (or the segmentation is
   explained), no empty required cells, no identifiers that failed the lookup. Failed lookups
   are listed by row for the owner, not silently dropped.
4. Deliver the file in the platform's format plus a three-line summary: platform, rows,
   transformations applied.
5. When a platform rejects a file or its spec has changed, update the reference in the same
   session — the correction is the valuable part.

## Rules

- One platform per output file. A "universal" export is how the DMA code/name error happens.
- Keep the original export untouched; transformations produce a new file.
