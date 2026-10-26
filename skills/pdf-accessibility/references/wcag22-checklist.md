# WCAG 2.2 A/AA for PDF documents

Applied through W3C WCAG2ICT (non-web documents). For each criterion record one of:
**Supported** (with evidence), **Not supported** (with the failure), **Pending** (named manual
test still to do), **Not applicable** (the triggering content is absent). 4.1.1 Parsing was
removed in WCAG 2.2; assess it only if an older version is mandated.

| SC | Lvl | What to check in the PDF | Evidence from this skill |
|---|---|---|---|
| 1.1.1 Non-text Content | A | Meaningful images have accurate alt/text equivalents; decorative ones are artifacts; image-of-text has real text | `validate` figures; figure sheets; transcript |
| 1.2.1–1.2.5 Media | A/AA | Captions/descriptions for embedded audio/video | usually N/A |
| 1.3.1 Info and Relationships | A | Headings, lists, tables (headers, scope), links, form labels are tagged with the right roles | veraPDF; `validate` headings/lists/tables; transcript |
| 1.3.2 Meaningful Sequence | A | Tag order = logical reading order; columns, sidebars, captions in place | transcript read-through; `coverage` |
| 1.3.3 Sensory Characteristics | A | Instructions don't rely only on shape, colour, position ("box on the right") | manual read; owner notes |
| 1.3.4 Orientation | AA | No orientation lock | N/A for static PDF unless forced |
| 1.3.5 Identify Input Purpose | AA | Form fields collecting personal data identify purpose | forms only |
| 1.4.1 Use of Color | A | Colour is not the only carrier of meaning (status, alignment, required) | words added via ActualText/alt; visual issue remains in repair |
| 1.4.2 Audio Control | A | — | N/A |
| 1.4.3 Contrast (Minimum) | AA | Text ≥ 4.5:1, large text ≥ 3:1 | `validate --contrast` (estimate; confirm with a colour picker) |
| 1.4.4 Resize Text | AA | Readable at 200% in the reader | manual (Acrobat zoom); HTML check in rebuild |
| 1.4.5 Images of Text | AA | No images of text except logos/essential | repair: text layers help AT only → flag; rebuild: Supported |
| 1.4.10 Reflow | AA | Usable at 400% / 320 CSS px without two-way scrolling | PDF: Acrobat Reflow (needs good tags), manual; HTML: `render_pdf.cjs` layout |
| 1.4.11 Non-text Contrast | AA | Meaningful graphics and UI parts ≥ 3:1 | manual on charts/icons/form fields |
| 1.4.12 Text Spacing | AA | No loss with increased spacing | HTML: automated; PDF: generally N/A per WCAG2ICT |
| 1.4.13 Content on Hover or Focus | AA | — | N/A |
| 2.1.1 Keyboard | A | Links/fields reachable by keyboard | Tabs /S; manual Tab test |
| 2.1.2 No Keyboard Trap | A | — | manual |
| 2.1.4 Character Key Shortcuts | A | — | N/A |
| 2.2.1/2.2.2 Timing, Pause | A | — | N/A |
| 2.3.1 Three Flashes | A | — | N/A for static |
| 2.4.1 Bypass Blocks | A | Headings/bookmarks allow skipping repeated content; furniture is artifact | headings; outlines; artifacts |
| 2.4.2 Page Titled | A | Descriptive title shown in title bar | `validate` metadata |
| 2.4.3 Focus Order | A | Tab order follows structure | Tabs /S; manual |
| 2.4.4 Link Purpose (In Context) | A | Link text/Contents meaningful in context | `validate` links |
| 2.4.5 Multiple Ways | AA | Within a document set; bookmarks/TOC help | context-dependent |
| 2.4.6 Headings and Labels | AA | Headings describe their sections | manual read of heading list |
| 2.4.7 Focus Visible | AA | Reader shows focus | manual in target reader |
| 2.4.11 Focus Not Obscured (Min) | AA | — | usually N/A |
| 2.5.1–2.5.4, 2.5.7 Pointer/motion | A/AA | — | N/A |
| 2.5.8 Target Size (Min) | AA | Link/control targets ≥ 24×24 CSS px or exceptions (inline) | manual for non-inline links/buttons |
| 3.1.1 Language of Page | A | Catalog /Lang correct | `validate` metadata |
| 3.1.2 Language of Parts | AA | Passages in other languages have /Lang | plan `lang` per element |
| 3.2.1–3.2.2 On Focus/Input | A | No context change on focus/input | forms/scripts only |
| 3.2.3/3.2.4 Consistent Nav/Identification | AA | Within a document set | context-dependent |
| 3.2.6 Consistent Help | A | — | document sets only |
| 3.3.1–3.3.4, 3.3.7, 3.3.8 Input | A/AA | Forms: errors, labels, prevention, redundant entry, authentication | forms only |
| 4.1.2 Name, Role, Value | A | Links and form fields expose name/role/value | veraPDF; forms manual |
| 4.1.3 Status Messages | AA | — | N/A |

Section 508 (US federal) incorporates WCAG 2.0 AA; meeting 2.2 AA covers it, but report
against the version the organization mandates.
