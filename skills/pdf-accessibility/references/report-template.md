# <Document title>: accessibility remediation report

Prepared <date>. Target: WCAG 2.2 Level AA (via WCAG2ICT) and PDF/UA-1. **This is a
remediation record, not a conformance claim, certification or VPAT/ACR.**

## Outcome
One paragraph: which deliverables, which path (repair / rebuild / both) and why, the
validation headline (veraPDF result, visual identity, coverage), and what is pending.

## Deliverables
- `<name>-accessible.pdf`: layout-preserving repair (same pages and appearance).
- `<name>-reading-edition.pdf` / `.html`: rebuilt edition (if produced).
- `validation/VALIDATION.md`, `validation/screenreader.txt`: evidence.

## What was done
Bulleted, concrete: metadata; figures (N decorative artifacted, N alt written, auto-alt
replaced); headings (counts per level); reading order (pages re-ordered, column joins);
lists/tables rebuilt; OCR text layers (pages); links; colour-only meaning put in words.

## Validation
| Check | Before | After |
|---|---|---|
| veraPDF PDF/UA-1 | rules failed / checks failed | … |
| Headings | … | … |
| Figures without alt | … | … |
| Visual diff vs source | — | identical / N pages |
| Text coverage | — | n/n (deliberate omissions listed) |
| Contrast estimate | … | … |

## Source issues for the owner
Numbered: hidden/conflicting text, typos, contradictions, incomplete sentences, unverifiable
links, low contrast that a repair cannot change, colour-only meaning visible to sighted users.

## Not done / limits
What automation could not establish; tests not run; features out of scope (forms, media).

## WCAG 2.2 A/AA matrix
Use `wcag22-checklist.md`: one row per criterion with Supported / Not supported / Pending /
Not applicable and the evidence.

## Required acceptance steps
From `manual-review.md`, tailored to this document.

## Local processing
Tools and versions (veraPDF, Tesseract, pikepdf, Chromium, axe-core). State that no
document content left the machine and that links were not visited.

## Continuation brief (when work will be picked up later)
Write this as `HANDOFF.md` beside the deliverables when anything is left for another
session or person:
- **Request and constraints:** the document, its source SHA-256, upload restrictions, the
  target standard (confirmed or assumed), what local work is already authorized.
- **Current result:** final files with hashes and page counts (`manifest.py`), repair or
  rebuild, what changed in layout or pagination.
- **Evidence:** validator and version, source-to-model proofreading status, coverage
  method and its limits, visual review, contrast, HTML checks, AT tests run or not run.
- **Open questions:** hidden or conflicting text, uncertain OCR, incomplete sentences,
  unverified links, and which version the output follows.
- **How to continue:** the next checks in order of value, the exact commands, what each
  script overwrites, case-specific assumptions (tag ids, coordinates), and which inputs
  (OCR, plan, content model) to reuse rather than regenerate.
- **Tool record:** tools actually run with versions, failed attempts and their fixes;
  tools only considered go in a separate sentence.
- **Completion boundary:** what can be concluded now, and what is still pending.
