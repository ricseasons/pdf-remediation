# Repair or rebuild?

Read `audit/AUDIT.md` and the page renders, then decide per document (and say why in the report).

## Repair in place when
- The PDF is tagged and the text is real text (Word, PowerPoint, InDesign exports).
- The visual design must be preserved (official, signed, branded or legally referenced documents).
- Problems are structural: missing alt, decorative figures tagged as content, wrong or
  missing headings, broken reading order, layout tables, untagged links, metadata.
- Image-of-text regions are limited and can get an invisible OCR text layer.

Repair keeps the rendering pixel-identical (`validate.py` proves it with `visual_diff`).
It cannot fix design-level failures: low colour contrast (1.4.3), meaning carried only by
colour or position *visually* (it can add words for AT, not for sighted users), images of
text for sighted low-vision users (1.4.5), or reflow (1.4.10). Report these to the owner
and offer the rebuild.

## Rebuild when
- The PDF is untagged, scanned, or the tag tree is unrecoverable.
- Most content is images of text, or the layout cannot be read in any sensible linear order.
- The audience needs reflow/zoom (WCAG 1.4.10) or the owner wants an HTML alternative.
- Contrast or colour-only meaning is pervasive and the owner accepts a redesign.

Rebuild changes pagination and appearance. Keep source page numbers, add an edition note,
and get owner acceptance of the content. An HTML/PDF reading edition is only a conforming
alternate version if it is equivalent, kept current and discoverable from the original.

## Both
Often the right answer for public documents: repair the original for fidelity and
publish the reading edition alongside it.

## Out of scope for these scripts (handle manually, say so)
- Fillable forms (field names/tooltips, tab order, required state, error handling).
- Embedded audio/video, JavaScript, 3D, attachments.
- Encrypted files that forbid content extraction (ask the owner for an unlocked copy).
- Languages that need complex shaping in invisible text layers: put the correct text in
  ActualText (repair does this automatically for non-Windows-1252 characters).
