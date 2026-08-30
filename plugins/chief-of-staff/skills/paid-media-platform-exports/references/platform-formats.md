# Platform export formats

The memory of `paid-media-platform-exports`. One section per platform. Every claim carries a
"verified on" date; a section marked **unverified** must be confirmed against the platform's
current bulk-upload documentation or a known-good past upload before a file is produced from
it, and the confirmation recorded here.

What each section records:

- **Geo identifier convention** — DMA code or DMA name (and whose naming: Nielsen name
  strings differ from some platforms' display names), zip handling, and the lookup source.
- **Columns** — required columns, exact header names, order sensitivity.
- **File shape** — CSV/TSV/XLSX, encoding, one file per campaign or combined, row limits.
- **Rejection behaviors** — what the platform silently accepts but mis-applies (the dangerous
  case) versus what it rejects loudly.

---

## Known so far

The evidenced facts this reference starts from, ahead of per-platform verification:

- Approximately five platforms receive reformatted PMP targeting exports, each with its own
  format quirks.
- The canonical divergence is the geo identifier: at least one platform requires the DMA
  **code** where another requires the DMA **name**. A file using the wrong one can upload
  cleanly and target wrongly — this is the error class the whole skill exists to prevent.
- Per-platform export templates have been proposed as a P1 improvement inside PMP itself;
  until that ships, this reference and the skill are the template.

---

## Outbrain — unverified

Pilot network for the geo-coverage alerting work; likely the first section to verify.

## Platform 2 — unverified

## Platform 3 — unverified

## Platform 4 — unverified

## Platform 5 — unverified

<!-- Add a dated section per platform as each format is confirmed. Do not delete a platform's
     section when it changes — date the old rule and add the new one, so a file produced last
     quarter can still be explained. -->
