# Alt text and artifact decisions

Decide from the page render, in context. Write for someone listening to the document.

## Decorative → artifact
Background art, stock photos that only set a mood, divider rules and shapes, repeated
logos/seals on every page, icons next to a text label that says the same thing, page
furniture (running headers/footers, page numbers, slide taglines), text hidden behind
other content (report it). Artifacts are not read and do not need alt.

## Meaningful → alt (or text)
| Image | What to write |
|---|---|
| Photo that is the subject | Who/what and why it matters here: "Photo of Dan Berger". Not "image of a man in a suit". |
| Logo as publisher identity (once) | The organisation name: "Bureau of the Fiscal Service". |
| Icon that is the only label | Its function or meaning: "Aligned", "Download". |
| Chart | Type, subject, takeaway, then the data or a pointer to a data table: "Bar chart of FY 2024–2026 spending: rose from $2.1M to $3.4M; largest increase in 2025." |
| Diagram / process | The structure in order (cycle, hierarchy, flow) and every label. |
| Org chart | Hierarchy in order: top role, who reports to whom. Long? Rebuild as nested list in a reading edition. |
| Image of text | The text verbatim. For more than a sentence or two, use a tagged OCR text layer instead of alt. |
| Signature | "Signed, Name" when the signature matters. |
| Map | What it shows and the key facts it conveys, not every street. |

## Style
- Don't start with "Image of", "Picture of", "Graphic of" (a screen reader already says "graphic").
- Usually under ~150 characters; complex images may need more, or a text alternative nearby.
- Use the document's terminology, spelling and capitalisation; end with a period.
- Don't repeat the caption or adjacent text verbatim; complement it.
- Never use file names, "Description automatically generated", "AI-generated content may be
  incorrect", or placeholders. `validate.py` flags these.
- If you cannot tell what an image means (internal jargon, unclear data), write your best
  factual description and list it for owner review.

## Colour, shape and position
If meaning is carried by colour, icon or position (a shaded cell = "aligned", red = overdue,
"see the box on the right"), put the meaning in words: ActualText on the element ("Planning
& Prioritization: aligned"), alt on the icon, or a list/table that states it. Then record the
visual issue (WCAG 1.4.1, 1.3.3) for the owner, because sighted users still see colour only.
