# veraPDF PDF/UA-1 failures and fixes

veraPDF implements the machine-checkable Matterhorn Protocol conditions. The fixes below
are what `repair.py` does automatically (A) or what the plan must say (P).

| Clause-test | Meaning | Fix |
|---|---|---|
| 5-1 | No PDF/UA identifier in XMP | A: `pdfuaid:part=1` |
| 7.1-3 | Content neither tagged nor artifact | A: untagged painting → Artifact. P: if it is real content, tag it (text layer or role) |
| 7.1-8/9 | Missing XMP metadata / dc:title | A: metadata from plan title |
| 7.1-10 | DisplayDocTitle not true | A |
| 7.1-11/12 | Suspect/Marked flags | A: `MarkInfo/Marked true` |
| 7.2-* | Structure type misuse (TR outside Table, LI outside L, irregular rows, …) | A: rows padded, LI bodies. P: fix roles or rebuild the table/list |
| 7.3-1 | Figure without Alt/ActualText | P: alt, or artifact if decorative |
| 7.4.2-1 | Headings don't start at H1 / no headings | P: one H1, nested levels |
| 7.4.4-* | Numbered headings out of sequence | P: correct levels |
| 7.5-1/2 | TH without Scope / headers | A: Scope from position. P: `header_rows`/`header_cols` |
| 7.9-1 | Note without ID | P: add ID or retag |
| 7.10-1/2 | Optional-content config without Name / AS key | A: Name. AS: fix manually |
| 7.11-1 | Embedded file spec lacks F/UF | manual |
| 7.15-1 | XFA form | out of scope: convert to AcroForm |
| 7.16-1 | Encryption blocks AT | ask owner for unencrypted file |
| 7.18.1-2 | Annotation without Contents/Alt | A for links; P via `link_text` |
| 7.18.3-1 | Page with annotations lacks Tabs /S | A |
| 7.18.4-* | Widget not inside Form element | manual (forms) |
| 7.18.5-1/2 | Link not in Link element / no Contents | A |
| 7.20-* | XObject reference rules | manual (rare) |
| 7.21.3.x | CIDSystemInfo / CMap problems | re-export from source app, or rebuild |
| 7.21.4.1 | Font not embedded | rebuild, or re-export with embedding; invisible (Tr 3) text is exempt |
| 7.21.4.2 | Incomplete CIDSet | A: CIDSet removed (optional key) |
| 7.21.7 | Glyphs without Unicode mapping | add ToUnicode (manual) or ActualText on the element (P) |

Passing veraPDF does not cover the human-checked Matterhorn conditions: correct reading
order, appropriate alt text, correct heading levels, semantically correct tags, logical
table headers, meaningful link text, colour/contrast, and so on. Those are in
`manual-review.md`.
