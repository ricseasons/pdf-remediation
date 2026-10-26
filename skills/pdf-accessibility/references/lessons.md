# Lessons from real remediations

Symptoms that misled earlier sessions, what they turned out to be, and what to do. They
come from two independent passes over the same slide-exported operational plan (one
rebuilt a reading edition with pypdf and Apple Vision, one repaired the original with this
skill's scripts) plus a few earlier documents. Treat them as things to check, not as
defects every PDF has.

## Content and source fidelity

| Symptom | What it was | Do this |
|---|---|---|
| Hundreds of figures without alt text | Mostly decorative shapes, plus text and headings drawn as vector paths | Classify first (`figure_sheets.py`, `draft_plan.py`). Identical bulk alt text never restores headings, lists or tables |
| Selectable text under an org chart | Superseded names hidden beneath the visible chart image | Follow the visible version, artifact the hidden text, list it as an owner question. Never merge the two versions |
| A heading missing from extracted text | Vector-outlined lettering already marked Artifact | `audit.py` uses vector bboxes too. Look at the render, not only at the text |
| Words run together after extraction | Characters joined in drawing order | Rebuild words from geometry (pdfplumber does this). Check spacing in the transcript |
| One bullet split across two P tags; a message running across two columns | Layout fragments, not semantic units | `merge` in the plan, or join in the content model, after looking at the page |
| Milestone "tables" made of loose text boxes | Number, description and date are separate boxes in columns | Pair rows by vertical position, assert equal counts and 1..n numbering, then check every pair by eye |
| A "Table" tag that is only a decorative strip | Tag names describe drawing, not meaning | Classify from meaning: layout grids become lists or plain structure |
| A matrix with icons floating next to its cells | Icons are separate figures outside the table | Pad the table and `place` the icons in their cells with alt text. Describe an unmarked cell as unmarked; don't invent "No" |
| All expected strings found in the output | This only proves model-to-output agreement | Proofread source-to-model separately (pages that were OCR'd, names, numbers, dates, every table pairing) |

## OCR

| Symptom | What it was | Do this |
|---|---|---|
| Tesseract misses fine print on slide pages | Small text at ordinary DPI | On a Mac use `ocr.py --engine vision`; elsewhere raise `--dpi` or OCR a zoomed `--region` |
| Vision fails with a CVPixelBuffer error | The process lacked OS access, not bad input | Rerun with the needed permission, or switch engine. Never fall back to an online OCR |
| OCR boxes land in the wrong place | Vision boxes are bottom-left and normalized; page rotation and crop boxes shift coordinates | `ocr.py` converts to PDF points (top-based) for unrotated pages; check rotated or cropped pages by overlaying |
| OCR "fixed" a typo or a name | Language correction | Correction is off in both engines. Keep source typos and report them |

## Tagged export (rebuild path)

| Symptom | Fix | Guardrail |
|---|---|---|
| Chrome's tagged PDF fails PDF/UA | `finalize.py`: LI children into LBody, Strong/Em to Span, link Contents, artifact untagged furniture, metadata, `/Tabs /S` | Never ship the raw Chrome export. Re-run veraPDF after every change |
| Playwright has no browser binary | `render_pdf.cjs` falls back to installed Chrome, then Edge | Record which browser produced the PDF |
| Skip link changes the URL but focus stays put | `main` needs `tabindex="-1"` (`build_html.py` does this) | `render_pdf.cjs` checks the focused element, not the URL |
| No page overflow at 320 px, but table words crushed into fragments | Tables squeezed to fit | Look at the 320 px screenshot. Give wide tables a labelled, focusable scroll region; the script checks ArrowRight scrolls it and Tab leaves it |
| Isolated headings and fragments in print | Global break-avoid rules don't hold short groups together | Targeted keep-with-next groups and column widths, then look at every printed page |
| Link description cut short | Text collected from one rectangle of a wrapped link | Use the link's full semantic label (the content model has it) |

## Repair path

| Symptom | Fix |
|---|---|
| PDF/UA fails on a font CIDSet | Remove only a CIDSet proven inconsistent with the embedded subset. Never delete glyph data or ToUnicode maps to silence a checker |
| Validator passes, but footer or label text is low contrast | PDF/UA does not test contrast. `validate.py --contrast` estimates it. Design colours go to the owner unless they agree to a change |
| Untagged content looked like page numbers only | Untagged graphics can be outlined words | `validate.py` lists untagged text and veraPDF flags any untagged content, graphics included. Look at what each draws before wrapping it as Artifact |

## Process

- **Continue, don't restart.** When earlier work exists (a handoff, an OCR run, a content
  model), read it first and reuse it. Redo a step only for a specific defect you can name.
- **Stale evidence.** Render into a fresh folder for each revision. Old PNGs from an export
  with a different page count once passed for current pages. Run `manifest.py` last, and
  never carry earlier counts or hashes over to a changed file.
- **Script names.** A helper named `inspect.py` shadowed the standard library and broke
  imports. Use specific names.
- **Machine paths.** Keep absolute runtime paths in the case handoff, not in scripts. These
  scripts take paths as arguments and find tools via `setup.sh`, `PLAYWRIGHT_MODULE`,
  `AXE_PATH` and `VERAPDF`.
- **Case scripts don't generalize.** A previous case's builder hardcodes tag ids, phrases
  and coordinates. Read it for its patterns (see `examples/build_plan_example.py`), never
  run it on a new source revision unchanged.
