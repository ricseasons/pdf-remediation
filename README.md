# pdf-remediation

A Claude skill for remediating PDFs to **WCAG 2.2 AA** and **PDF/UA-1**, entirely on the local
machine. Open-source tools do the mechanics (veraPDF, pikepdf, PyMuPDF, pdfplumber, Tesseract,
Chromium, axe-core); Claude makes the judgement calls a human remediator would: what each image
means, which graphics are decorative, what the headings and reading order are, what a table's
headers are, and where colour carries meaning that has to be put into words.

The skill lives in [`skills/pdf-accessibility/`](skills/pdf-accessibility/SKILL.md).

## Two paths

- **Repair (layout-preserving).** Edits the existing tag tree in place from a JSON remediation
  plan: artifacts, alt text, headings, reading order, merges, lists, table fixes, link tagging,
  invisible OCR text layers for image-of-text, plus automatic PDF/UA fixes. The output renders
  pixel-identical to the source, and `validate.py` checks that.
- **Rebuild (reading edition).** Content model → accessible HTML → Chromium tagged PDF → PDF/UA
  finishing, with axe-core, reflow, text-spacing, zoom and keyboard checks.

## Quick start

```bash
bash skills/pdf-accessibility/scripts/setup.sh
S=skills/pdf-accessibility/scripts
python3 $S/audit.py input.pdf WORK                  # inventory, tag trees, veraPDF baseline, page renders
python3 $S/figure_sheets.py input.pdf WORK          # contact sheets of every figure
python3 $S/draft_plan.py WORK --title "Real title"  # mechanical decisions; TODOs for judgement
# ... Claude reviews pages and writes WORK/plan.json ...
python3 $S/repair.py input.pdf WORK/plan.json out.pdf --workdir WORK
python3 $S/validate.py out.pdf WORK/validation --source input.pdf --contrast
```

To install as a Claude Code skill, copy or symlink `skills/pdf-accessibility` into
`~/.claude/skills/` (personal) or `.claude/skills/` (project).

## Test results

On a 22-page PowerPoint-exported operational plan (414 figure tags, no headings, image-of-text
pages, milestone "tables" built from loose text boxes):

| | Source | Repaired (same layout) | Reading edition |
|---|---|---|---|
| veraPDF PDF/UA-1 | 9 rules, 401 checks failed | 0 failed (72,103 checks passed) | 0 failed (184,465 checks passed) |
| Rendering vs source | — | identical, all 22 pages | new layout, 38 pages |
| Headings | 0 | 110 (one H1, no skipped levels) | 118 |
| Figures without alt | 344 | 0 | 0 |
| axe-core (HTML) | — | — | 0 violations |

The test document is not in this repository. Automated results are not a conformance claim; see
`references/manual-review.md` for the screen-reader, reflow and owner checks still required.
