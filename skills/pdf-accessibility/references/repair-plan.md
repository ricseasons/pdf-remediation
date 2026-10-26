# Repair plan schema (`repair.py`)

A plan is JSON. Element ids are **object numbers in the source PDF** as printed by
`audit.py` (`tree-NN.txt`, `structure.json`). The plan is always applied to the original
source, so it can be edited and re-applied any number of times. Keys starting with `_`
and `why` fields are ignored and are a good place for reasoning notes.

```jsonc
{
  "metadata": {"title": "Real title", "lang": "en-US", "author": "...", "subject": "...", "keywords": "..."},
  "pdfua_part": 1,

  // Fix the one-paragraph-per-line or split-title problem. First id keeps the role; others are absorbed.
  "merge": [[2995, 2996], [2886, 2887, 2888]],

  // New grouping elements. children are moved into the new element at the first child's position.
  "new": [{"name": "sidebar", "role": "Div", "parent": 2735, "children": [2712, 2720]}],

  // Lists from loose paragraphs. Items are ids, or {"lbl": id, "body": [ids]} to keep a bullet/number as Lbl.
  "lists": [{"name": "p12-risks", "items": [{"lbl": 2133, "body": [2134]}, 2136], "ordered": false,
             "numbering": "Disc"}],

  // Reading order per parent. Listed children (ids or names from new/lists) are moved under the parent
  // in this order; "*" marks where the remaining children go (default: after the listed ones).
  "order": {"2825": [2823, 2808, 2809, "*"]},

  // Per-element edits.
  "elements": {
    "2997": {"role": "H1", "actualtext": "FY 2027 Operational Plan"},   // ActualText replaces content for AT
    "2883": {"alt": "Photo of Dan Berger"},
    "2990": {"artifact": true, "why": "cover photograph"},              // rewrites content as /Artifact, removes element
    "2938": {"unwrap": true},                                           // replace element by its children
    "2546": {"strip_graphics": true, "unwrap": true},                   // artifact own shapes, keep child text
    "1234": {"lang": "es"}, "1235": {"expansion": "Bureau of the Fiscal Service"},
    "1236": {"role": "TH", "scope": "Row"},
    "1237": {"attributes": {"O": "/Layout", "Placement": "/Block"}}
  },

  // Apply one decision to every member of a visual group from figures/groups.json.
  "figure_groups": {"G6": {"artifact": true}},

  // Remap roles everywhere, applied before element edits.
  "retag_roles": {"TextBox": "Div"},
  // Replace every element with this source role by its children (slide TextBox/Group wrappers).
  "unwrap_roles": ["TextBox", "Group"],

  // Invisible tagged text over image-of-text or outlined text. Blocks take text plus OCR line ids
  // (from ocr.py) or an explicit bbox [x0, top, x1, bottom] in points. role L builds a list.
  "text_layers": [{"page": 7, "parent": 2647, "after": 2645, "blocks": [
      {"role": "H3", "text": "Strategic & Operational Planning", "ocr": ["p7-l8", "p7-l9"]},
      {"role": "P", "text": "Define the future…", "bbox": [103, 193, 258, 208]},
      {"role": "L", "items": [{"text": "First item", "ocr": ["p7-l20"], "lbl": "•"}]}]}],

  // Table fixes, keyed by Table id. pad: add empty cells to short rows (default true).
  // place: [row, col, [ids]] moves stray content (icons, text drawn over a grid) into a cell, 0-based.
  "tables": {"461": {"header_rows": 1, "header_cols": 1, "place": [[1, 2, [453]]], "summary": "optional"}},

  // Override link descriptions (annotation object number -> text).
  "link_text": {"2519": "Full list of FY 2026 accomplishments"},

  // Disable automatic fixes if one is wrong for a document.
  "auto": {"metadata": true, "optional_content": true, "cidset": true, "links": true, "tables": true,
           "lists": true, "untagged": true, "prune": true}
}
```

## Order of operations

merge → new → lists → order → figure_groups → text_layers → elements (retag_roles first) →
strip_graphics → unwrap → artifact → automatic fixes → prune empty → save.

Consequences: an id can be moved by `order` and still be unwrapped later; a merged-away id
cannot be edited (draft entries for it are skipped); `text_layers` parents/after refer to
elements as they stand after `order`.

## Automatic fixes (every run)

| Fix | PDF/UA / WCAG |
|---|---|
| Catalog `/Lang`, `MarkInfo/Marked`, `ViewerPreferences/DisplayDocTitle`, Info + XMP title, XMP `pdfuaid:part` | UA 7.1-8/9/10, 5; WCAG 2.4.2, 3.1.1 |
| Optional-content configuration names | UA 7.10 |
| Remove incomplete `CIDSet` streams | UA 7.21.4.2 |
| Link annotations: Reference/Span → Link, OBJR wrapped in Link, untagged links attached to the text under them, `Contents` from visible text, `Tabs /S` | UA 7.18.1, 7.18.3, 7.18.5; WCAG 2.4.4 |
| Tables: pad short rows, TH `Scope` | UA 7.2 (row regularity), 7.5 |
| `LI` children normalised to `Lbl`/`LBody`; `ListNumbering` when labels exist | UA 7.2; UA-2 8.2.5.25 |
| Painting operators outside marked content → `/Artifact` | UA 7.1-3 |
| Empty elements pruned (except table cells) | tidiness |

## Gotchas

- Object numbers change when pikepdf saves; audit the output with `--trace-ids` to map back.
- Artifacting an element that contains a link annotation is refused (annotations must stay
  tagged); unwrap or retag it instead.
- ActualText replaces all descendant text for AT. Put it on the smallest element that needs it.
- Invisible text uses an embedded WinAnsi subset of Liberation Sans, DejaVu Sans or Arial (fontTools;
  `PDF_A11Y_FONT` picks another TrueType file). PDF/UA-1 exempts rendering mode 3 from embedding,
  but Section 508 checkers flag any unembedded font, so it falls back to Helvetica only with a warning;
  characters outside Windows-1252 are kept correct through ActualText automatically.
