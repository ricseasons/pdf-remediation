# Manual acceptance review

Automated checks (veraPDF, `validate.py`, axe) cover a fraction of WCAG. Before anyone
claims conformance, a person completes these and records results in the report.

## 1. Screen reader read-through (required)
Use the organization's supported combination, typically NVDA + Acrobat Reader (Windows),
JAWS + Acrobat, or VoiceOver + Preview (macOS, weaker PDF support).
- Read the whole document top to bottom. Everything is read once, in a sensible order;
  nothing decorative is announced; no "graphic" without a description.
- Navigate by headings (H / 1–6 keys): the heading list is an outline of the document.
- Navigate by lists (L) and tables (T): list item counts are right; in tables, row/column
  headers are announced when moving cell to cell.
- Links (Tab or K): every link name makes sense; internal links go to the right place.
- Compare against `validation/screenreader.txt`; differences point at reader quirks.

## 2. Visual and reflow
- Acrobat: View → Zoom → Reflow; check order and that nothing is lost (1.4.10, 1.3.2).
- Zoom to 200% and 400%: text stays readable, no clipped content (1.4.4).
- Check contrast findings from `validate --contrast` with a colour picker (1.4.3, 1.4.11).
- Look for meaning carried by colour/position that sighted users can't get otherwise (1.4.1, 1.3.3).

## 3. Keyboard
- Tab through all links and fields: order follows reading order, focus is visible (2.1.1, 2.4.3, 2.4.7).

## 4. Content owner
- Proofread every OCR'd or transcribed passage against the original.
- Confirm alt text and text equivalents say what the author intends (1.1.1).
- Resolve the source issues listed in the report (contradictions, hidden text, typos).
- Approve any editorial additions (descriptions, "aligned/not aligned" wording).

## 5. Publication
- Title shown in the browser/reader tab; file name meaningful.
- If an HTML or reading edition is the accessible alternative: equivalent, kept current,
  and reachable from the original (WCAG conforming alternate version).
- Re-run `validate.py` on the final published file after any edit.
