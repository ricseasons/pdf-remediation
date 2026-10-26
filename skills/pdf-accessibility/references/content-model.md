# Content model (`build_html.py`, rebuild path)

The content model is the whole document as structured data in reading order. Write it
yourself from extracted text, corrected OCR and your reading of the page renders.

```json
{
  "title": "FY 2027 Operational Plan",
  "kicker": "Office of the Chief Financial Officer (OCFO)",
  "subtitle": "Accessible reading edition",
  "lang": "en-US",
  "edition_note": ["Prepared from …; layout changed; diagrams described in text."],
  "toc": true, "show_source_pages": true, "footer": "End of reading edition.",
  "sections": [
    {"title": "Message from the CFO", "source_page": 3, "blocks": [
      {"role": "p", "text": "Paragraph with an inline [descriptive link](https://example.gov)."},
      {"role": "h3", "text": "Subheading"},
      {"role": "ul", "items": ["one", {"text": "two", "items": ["nested"]}]},
      {"role": "ol", "items": ["first", "second"]},
      {"role": "table", "caption": "Priority 1 milestones", "headers": ["#", "Milestone", "Target"],
       "rows": [["1", "Complete UAT …", "FY 2027 Q1"]], "row_headers": true},
      {"role": "figure", "src": "img/chart.png", "alt": "Bar chart: spending rose from $2M in 2024 to $3M in 2026."},
      {"role": "figure", "src": "img/divider.png", "decorative": true},
      {"role": "description", "title": "Text equivalent of the organization chart", "blocks": [
        {"role": "ul", "items": [{"text": "CFO: Dan Berger", "items": ["Deputy CFO: …"]}]}]},
      {"role": "note", "text": "Owner review: source says “Support Model” here and “Oversight Model” on page 15."},
      {"role": "quote", "text": "…", "cite": "…"},
      {"role": "link", "text": "OCFO Collaboration Hub", "href": "https://…"}
    ]}
  ]
}
```

Rules:
- Section titles are H2; the document title is the only H1. Use h3/h4 inside sections, no skips.
- Every table has headers; use `row_headers` when the first column labels the row.
- Put source page numbers in `source_page` so reviewers can compare.
- Editorial additions (descriptions, notes) must be recognisable as such; never invent content.
- Embed images as files next to the HTML or as data URIs; nothing is fetched from the network.
- `--expected` writes every fragment so `validate.py --expected` can prove nothing was dropped.
- Extra CSS (`--css`) can tune print breaks; keep text contrast ≥ 4.5:1 and links underlined.
