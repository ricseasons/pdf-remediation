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
