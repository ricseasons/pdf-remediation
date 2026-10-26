#!/usr/bin/env python3
"""Rebuild path, step 0: draft a content model from a PDF's text (tagged or not).

Usage: draft_content.py INPUT.pdf OUT.json [--title "..."] [--lang en-US] [--ocr-dir WORKDIR/ocr]

Uses PyMuPDF text blocks with font sizes and simple rules: the largest text on a page
starts a section, larger-than-body lines become h3, lines starting with a bullet glyph
become list items, everything else is a paragraph. Pages with no text pull lines from
ocr.py output when --ocr-dir is given.

The draft is a starting point. Fix the reading order, headings, lists and tables by
looking at the page renders, add figures with alt text and text equivalents for charts,
then run build_html.py.
"""
import argparse
import json
import re
import statistics
from pathlib import Path

import pymupdf as fitz

BULLET = re.compile(r"^\s*([•●▪◦‣\-–*]|\d{1,2}[.)])\s+")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("out")
    ap.add_argument("--title")
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--ocr-dir")
    a = ap.parse_args()
    doc = fitz.open(a.input)
    pages = []
    sizes = []
    for i, page in enumerate(doc):
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            lines = b.get("lines", [])
            spans = [s for l in lines for s in l["spans"] if s["text"].strip() and s.get("alpha", 255)]
            if not spans:
                continue
            text = " ".join(" ".join(s["text"] for s in l["spans"]).strip() for l in lines).strip()
            size = max(s["size"] for s in spans)
            sizes += [s["size"] for s in spans]
            blocks.append({"text": re.sub(r"\s+", " ", text), "size": size, "y": b["bbox"][1], "x": b["bbox"][0]})
        if not blocks and a.ocr_dir:
            f = Path(a.ocr_dir) / f"page-{i + 1:02}.json"
            if f.exists():
                for l in json.loads(f.read_text())["lines"]:
                    h = l["bbox"][3] - l["bbox"][1]
                    blocks.append({"text": l["text"], "size": h, "y": l["bbox"][1], "x": l["bbox"][0], "ocr": True})
        pages.append(blocks)
    body = statistics.median(sizes) if sizes else 11
    sections = []
    for i, blocks in enumerate(pages, 1):
        if not blocks:
            continue
        blocks.sort(key=lambda b: (round(b["y"] / 4), b["x"]))
        top = max(blocks, key=lambda b: b["size"])
        title = top["text"] if top["size"] >= 1.3 * body else f"Page {i}"
        sec = {"title": title, "source_page": i, "blocks": []}
        items = []
        for b in blocks:
            if b is top and title == b["text"]:
                continue
            if re.fullmatch(r"(?i)page\s*\d+|\d{1,3}", b["text"]):
                continue
            if BULLET.match(b["text"]):
                items.append(BULLET.sub("", b["text"]))
                continue
            if items:
                sec["blocks"].append({"role": "ul", "items": items})
                items = []
            role = "h3" if b["size"] >= 1.2 * body and len(b["text"]) < 120 else "p"
            sec["blocks"].append({"role": role, "text": b["text"], **({"_ocr": True} if b.get("ocr") else {})})
        if items:
            sec["blocks"].append({"role": "ul", "items": items})
        sections.append(sec)
    out = {"title": a.title or (doc.metadata or {}).get("title") or "TODO title", "lang": a.lang,
           "edition_note": ["TODO: describe how this edition differs from the source."], "sections": sections}
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {a.out}: {len(sections)} sections from {len(pages)} pages (body text {body:.1f}pt). Review before building.")


if __name__ == "__main__":
    main()
