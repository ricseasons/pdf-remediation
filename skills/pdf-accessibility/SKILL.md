---
name: pdf-accessibility
description: Remediate PDFs to WCAG 2.2 AA and PDF/UA-1 locally. Use when asked to make a PDF accessible, fix tags, alt text, reading order, headings or tables in a PDF, prepare a Section 508 / ADA compliant PDF, or validate a PDF with veraPDF. Produces a layout-preserving repaired PDF and/or a rebuilt accessible reading edition, with validation evidence and a remediation report.
---

# PDF accessibility remediation

You are doing the work a professional PDF remediator does in Acrobat Pro, PAC and a screen
reader, with open-source tools plus your own judgement. The tools handle the mechanics;
**the judgement calls are yours**: what each image means, which graphics are decorative,
what the headings are, what order a person should hear things in, what a table's headers
are, and whether colour or position carries meaning that text must repeat.

Target: **WCAG 2.2 Level AA** (via W3C WCAG2ICT for non-web documents) and **PDF/UA-1
(ISO 14289-1)**. A veraPDF pass is necessary, not sufficient. Never call a document
"compliant" or "conformant"; say what was checked and what remains for human testing.

## Ground rules

- **Keep documents local.** Never upload a document, page image or extracted text to a
  web service, online converter, OCR API or external LLM. Everything below runs on the
  machine. Do not follow links found in the document; record them for the owner instead.
- **Never overwrite the source.** Work in a copy (`WORK/source.pdf`).
- **Do not change the author's words.** Fix extraction artifacts (broken hyphens, letter-
  spaced text) through ActualText; report typos, contradictions and incomplete sentences
  to the owner instead of correcting them.
- **Look before you decide.** Every alt text, artifact decision and reading order comes
  from viewing the page render (`Read` the PNG), not only from extracted text.
- **Hidden or conflicting content is an owner question.** Text under images, white-on-
  white text and stale layers get artifacted only with a note in the report.

## Setup (once per machine)

```bash
bash scripts/setup.sh          # pikepdf, PyMuPDF, pdfplumber, Tesseract, qpdf, veraPDF (Maven), Playwright, axe-core
bash scripts/setup.sh --check  # report what is missing
```
`S=<this skill>/scripts` in the commands below. Scripts are Python 3.10+ and Node 18+.

## Workflow

### 1. Intake and audit

```bash
mkdir -p WORK && cp INPUT.pdf WORK/source.pdf
python3 $S/audit.py WORK/source.pdf WORK          # inventory, tag trees, veraPDF baseline, page renders
```
Read `WORK/audit/AUDIT.md`, then look at every page render in `WORK/pages/`. Note for each
page: the visual title, columns, images that carry meaning, charts, tables, text that is
really an image, colour-coded information, repeated furniture (headers, footers, logos).

Ask the person (once, recommend defaults) only for what changes the outcome: the required
standard if not WCAG 2.2 AA / PDF/UA-1, and whether layout fidelity or a reading edition
matters more. Otherwise proceed with the decision guide below and say which you chose.

### 2. Choose the path (`references/decision-guide.md`)

| Source | Path |
|---|---|
| Tagged (Word/PowerPoint/InDesign export), real text | **Repair** in place. Keeps the exact design. |
| Tagged but with image-of-text pages | Repair + **invisible OCR text layers** for those pages; offer a reading edition too (WCAG 1.4.5). |
| Untagged, scanned, or tags beyond saving | **Rebuild**: content model → HTML → tagged PDF. Also offer the HTML. |
| Forms, multimedia, JavaScript | Out of scope for the scripts; remediate fields manually and say so. |

Doing both is often best: a layout-preserving original for people who need the official
document, and a reading edition that reflows.

### 3a. Repair path (layout-preserving)

1. **Figures.** `python3 $S/figure_sheets.py WORK/source.pdf WORK` then
   `python3 $S/draft_plan.py WORK --title "Real document title" --lang en-US`.
   The draft decides the mechanical cases (containers → unwrap, rules/backgrounds/repeated
   logos → artifact, page numbers → artifact) and marks the rest TODO.
   `python3 $S/figure_sheets.py WORK/source.pdf WORK --pending WORK/plan.draft.json`
   draws only the undecided figures. View each sheet; for anything unclear open
   `WORK/figures/crops/ID.png` and the page render. Write alt text per
   `references/alt-text.md`. Rewrite auto-generated alt ("Description automatically
   generated", "Logo", "Picture 3").
2. **Image-of-text and outlined text.** `python3 $S/ocr.py WORK/source.pdf WORK --pages 7,8`
   (Tesseract, local). Compare OCR with the render at zoom and correct it. Then add a
   `text_layers` entry: invisible tagged text (real headings, paragraphs, lists) placed
   over the image, and artifact the image. Vector-outlined headings that already have an
   MCID just get `role` + `actualtext`; outlined text that is only an artifact gets a
   one-block text layer.
3. **Structure, page by page.** Read `WORK/audit/tree-NN.txt` beside `pages/page-NN.png`.
   In the plan set: one H1 (document title), H2 per major section/slide title, H3/H4 below,
   with no skipped levels; `merge` text split by layout (titles over two lines, paragraphs
   across columns); `lists` for bullets typed as separate paragraphs (bullet glyph as Lbl);
   numbered rows as ordered lists or real tables; `order` for the reading sequence per
   page; `tables` for header rows/columns, padding and placing stray cell content.
   Where colour or an icon carries meaning, put the meaning in words (ActualText or alt).
   For repetitive templates (slide decks, forms of the same layout) write the plan with a
   short script using element geometry; `examples/build_plan_example.py` shows the pattern.
   Full schema: `references/repair-plan.md`.
4. **Apply and iterate.**
   ```bash
   python3 $S/repair.py WORK/source.pdf WORK/plan.json WORK/out.pdf --workdir WORK [--trace-ids]
   python3 $S/screenreader.py WORK/out.pdf -o WORK/transcript.txt
   ```
   Read the transcript top to bottom as if listening. Fix the plan, re-run (the plan always
   applies to the original source; ids are source object numbers). `--trace-ids` lets
   `audit.py WORK/out.pdf WORK2` show source ids on the output for a second look; never ship
   a traced file.

### 3b. Rebuild path (reading edition)

1. `python3 $S/draft_content.py WORK/source.pdf WORK/content.json --ocr-dir WORK/ocr` gives a
   rough first draft. Then make `WORK/content.json` right (`references/content-model.md`): every piece of content in
   reading order, with headings, lists, tables (headers + row headers), figures with alt or
   text equivalents, and descriptive links. Use extracted text for real-text pages and
   corrected OCR for image pages. Charts and diagrams become a `description` block with
   the data or structure in text; org charts become nested lists.
2. Render and finish:
   ```bash
   python3 $S/build_html.py WORK/content.json WORK/edition.html --expected WORK/expected.json
   node $S/render_pdf.cjs WORK/edition.html WORK/chrome.pdf WORK/html-checks.json --footer "Short title · Reading edition"
   python3 $S/finalize.py WORK/chrome.pdf WORK/edition.pdf --title "Title - Accessible Reading Edition"
   ```
   `render_pdf.cjs` blocks all network access, runs axe-core and the reflow, text-spacing,
   200% and keyboard checks. Fix every axe violation in the content model and rebuild.
3. Render the final PDF pages (`audit.py` writes `pages/`) and look at them: no clipped
   tables, no orphaned headings, sensible breaks.

### 4. Validate

```bash
python3 $S/validate.py WORK/out.pdf WORK/validation --source WORK/source.pdf --contrast        # repair
python3 $S/validate.py WORK/edition.pdf WORK/validation-ed --expected WORK/expected.json --contrast  # rebuild
```
Required to ship: `pdfua.ua1` PASS, metadata/headings/figures/lists/links/tables/untagged
not FAIL, `visual_diff` PASS for a repair. Every REVIEW item needs a decision: coverage
gaps must be deliberate artifacts, contrast findings in the source design go to the owner
(a repair cannot change colours without the owner's agreement), long alt text may need a
text alternative elsewhere. Use `ua2` only for PDF 2.0 output.

### 5. Report and hand off

Write `REMEDIATION-REPORT.md` from `references/report-template.md`: what was done, the
validation table, the WCAG 2.2 A/AA criterion matrix (`references/wcag22-checklist.md`),
source issues for the owner, and the manual acceptance steps in
`references/manual-review.md` (NVDA/JAWS/VoiceOver read-through, Acrobat reflow and 200%/
400% zoom, keyboard link test, owner proofreading of OCR and alt text). Deliver the PDF(s),
the HTML edition if built, the report, `validation/VALIDATION.md` and the transcript.

## Judgement guide (the part tools cannot do)

- **Decorative vs meaningful.** Ask: if this image vanished, would a reader lose
  information? Stock photos, background art, divider rules, repeated logos and icons
  beside a text label are decorative. Charts, diagrams, maps, signatures that matter,
  photos that are the subject, and icons that are the only label are meaningful.
- **Alt text.** Say what the image communicates in this context, not what it looks like.
  Charts: the takeaway plus the data (or a table elsewhere). Diagrams: the structure in
  order. Text in images: the text, verbatim. Don't start with "image of".
- **Headings** come from the visual hierarchy and meaning, not font size alone. A slide
  title is an H2 under the document H1; the same running title on continuation pages can
  stay a heading with "continued" only when the source shows it.
- **Reading order** follows how a sighted reader moves: title, intro, then columns top to
  bottom, left to right, sidebars after the content they support, captions with figures.
  Paragraphs split across columns are one paragraph.
- **Tables** need a header row and/or column; layout grids that only position things are
  not tables (turn them into lists or plain structure). Cells conveyed by colour or icons
  need words ("Aligned", "Not aligned").
- **Links** need text that makes sense in context; "link" or a bare URL gets a descriptive
  Contents/Alt, and the visible wording issue goes in the owner notes.
- **Use the strongest model available** for these decisions and look at pages at full
  resolution. When there are dozens of figures, decide in batches from the contact sheets;
  when a page is dense, crop and zoom (`ocr.py --region` writes crops too).

## Files

- `scripts/` — `audit.py`, `figure_sheets.py`, `draft_plan.py`, `ocr.py`, `repair.py`,
  `screenreader.py`, `draft_content.py`, `build_html.py`, `render_pdf.cjs`, `finalize.py`, `validate.py`,
  `setup.sh`, shared `pdfa11y.py`.
- `references/` — `decision-guide.md`, `repair-plan.md`, `content-model.md`, `alt-text.md`,
  `pdfua-fixes.md`, `wcag22-checklist.md`, `manual-review.md`, `report-template.md`.
- `examples/build_plan_example.py` — a real plan builder for a 22-page slide-export report.
