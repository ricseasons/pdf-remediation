#!/usr/bin/env python3
"""Rebuild path, step 1: render a content model as accessible, print-ready HTML.

Usage: build_html.py CONTENT.json OUT.html [--css extra.css]

CONTENT.json (see references/content-model.md):
{
  "title": "Document title", "lang": "en-US", "subtitle": "...", "edition_note": ["paragraph", ...],
  "running_footer": "Short title · Reading edition",   (used by render_pdf.cjs)
  "toc": true, "show_source_pages": true,
  "sections": [
    {"title": "Section heading (H2)", "source_page": 3, "id": "optional-id", "lang": "optional",
     "blocks": [
        {"role": "p", "text": "Inline [link text](https://…) markup is supported."},
        {"role": "h3", "text": "..."}, {"role": "h4", "text": "..."},
        {"role": "ul" | "ol", "items": ["text", {"text": "parent", "items": ["nested"]}]},
        {"role": "table", "caption": "...", "headers": ["..."], "rows": [["row header", "cell", ...]],
         "row_headers": true, "summary": "optional"},
        {"role": "figure", "src": "relative/or/data-uri.png", "alt": "...", "caption": "optional"},
        {"role": "figure", "src": "...", "decorative": true},
        {"role": "description", "title": "Text equivalent of the chart", "blocks": [ ...nested blocks... ]},
        {"role": "note", "text": "..."},
        {"role": "link", "text": "Descriptive link text", "href": "https://…"},
        {"role": "quote", "text": "...", "cite": "optional"}
     ]}
  ]
}
A plain list of sections (the Codex content-model.json layout) is also accepted.
"""
import argparse
import html
import json
import re
from pathlib import Path

CSS = """
:root{color-scheme:light}*{box-sizing:border-box}html{scroll-padding-top:1rem}
body{font:1.125rem/1.6 Arial,Helvetica,sans-serif;color:#172b3a;background:#fff;margin:0 auto;max-width:56rem;padding:2rem}
a{color:#064f80;text-decoration:underline;text-underline-offset:.16em;overflow-wrap:anywhere}
a:focus-visible,.table-wrap:focus-visible,main:focus-visible{outline:3px solid #111;outline-offset:4px}
a:focus-visible{background:#fff3b0}
.skip{position:absolute;left:-999px;top:0}.skip:focus{left:1rem;top:1rem;background:#fff;padding:.5rem;z-index:2}
h1,h2,h3,h4,h5{line-height:1.25;color:#143a52;break-after:avoid}h1{font-size:2.25rem}
h2{font-size:1.7rem;border-top:4px solid #1d6354;padding-top:1rem;margin-top:3rem}h3{font-size:1.25rem;margin-top:1.7rem}h4{font-size:1.08rem}
p,li{orphans:3;widows:3}li{margin:.45rem 0}ul,ol{padding-left:1.5rem}
.edition-note,.note{padding:1rem;border:1px solid #617789;background:#f0f5f6}
.source{font-size:.875rem;color:#435766}
.table-wrap{width:100%;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.94rem;line-height:1.45;margin:1rem 0 1.5rem}
caption{break-after:avoid;font-weight:bold;text-align:left;margin-bottom:.5rem}
th,td{border:1px solid #6b7b85;padding:.55rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{color:#172b3a;background:#e9f0f3}td{background:#fff}thead{display:table-header-group}tr{break-inside:avoid}
figure{margin:1.5rem 0}figure img{max-width:100%;height:auto}figcaption{font-size:.95rem;color:#2c3e4c}
.description{border-left:4px solid #1d6354;padding-left:1rem}
blockquote{border-left:4px solid #617789;margin-left:0;padding-left:1rem}
footer{border-top:1px solid #617789;margin-top:3rem;padding-top:1rem}
@media(max-width:500px){body{padding:1rem}h1{font-size:1.8rem}h2{font-size:1.45rem}table{font-size:.85rem}th,td{padding:.3rem}}
@page{size:Letter;margin:.65in .65in .7in}
@media print{body{font-size:11pt;line-height:1.45;padding:0;max-width:none}h1{font-size:26pt}h2{font-size:20pt;margin-top:0;padding-top:10pt}
h3{font-size:13pt;margin-top:16pt}h4{font-size:11.5pt}.skip{display:none}section{break-before:page}table{font-size:10pt}
th,td{padding:.3rem}.table-wrap{overflow:visible}.source{font-size:9pt}.cover{break-after:page}nav{break-after:page}footer{font-size:9pt}}
"""

LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def e(s, quote=False):
    return html.escape(str(s), quote=quote)


def inline(s):
    """Escape text, then turn [label](href) into links."""
    out, pos = [], 0
    for m in LINK.finditer(s):
        out.append(e(s[pos:m.start()]))
        out.append(f'<a href="{e(m.group(2), True)}">{e(m.group(1))}</a>')
        pos = m.end()
    out.append(e(s[pos:]))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "section"


def render_items(items, ordered):
    tag = "ol" if ordered else "ul"
    parts = []
    for it in items:
        if isinstance(it, dict):
            sub = render_items(it.get("items", []), it.get("ordered", False)) if it.get("items") else ""
            parts.append(f"<li>{inline(it.get('text', ''))}{sub}</li>")
        else:
            parts.append(f"<li>{inline(it)}</li>")
    return f"<{tag}>{''.join(parts)}</{tag}>"


def render(b, counter):
    role = b["role"]
    lang = f' lang="{e(b["lang"], True)}"' if b.get("lang") else ""
    if role in ("p", "h3", "h4", "h5", "h6"):
        return f"<{role}{lang}>{inline(b['text'])}</{role}>"
    if role in ("ul", "ol", "prioritylinks"):
        return render_items(b["items"], role == "ol")
    if role == "org":  # Codex layout: groups with children
        return "<ul>" + "".join(f"<li>{inline(g['name'])}" + (render_items(g["children"], False) if g["children"] else "") + "</li>"
                                for g in b["groups"]) + "</ul>"
    if role == "link":
        return f'<p><a href="{e(b["href"], True)}">{e(b["text"])}</a></p>'
    if role == "note":
        return f'<p class="note"{lang}>{inline(b["text"])}</p>'
    if role == "quote":
        cite = f"<p>— {inline(b['cite'])}</p>" if b.get("cite") else ""
        return f"<blockquote{lang}><p>{inline(b['text'])}</p>{cite}</blockquote>"
    if role == "table":
        counter["table"] += 1
        rh = b.get("row_headers", True)
        head = "".join(f'<th scope="col">{inline(h)}</th>' for h in b["headers"])
        body = ""
        for row in b["rows"]:
            cells = ""
            for i, v in enumerate(row):
                cells += f'<th scope="row">{inline(v)}</th>' if (i == 0 and rh) else f"<td>{inline(v)}</td>"
            body += f"<tr>{cells}</tr>"
        cap = e(b.get("caption", f"Table {counter['table']}"))
        return (f'<div class="table-wrap" role="region" tabindex="0" aria-label="{cap}"><table>'
                f"<caption>{cap}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")
    if role == "figure":
        if b.get("decorative"):
            return f'<img src="{e(b["src"], True)}" alt="" role="presentation">'
        cap = f"<figcaption>{inline(b['caption'])}</figcaption>" if b.get("caption") else ""
        return f'<figure><img src="{e(b["src"], True)}" alt="{e(b["alt"], True)}">{cap}</figure>'
    if role == "description":
        inner = "".join(render(x, counter) for x in b.get("blocks", []))
        title = f"<h4>{inline(b['title'])}</h4>" if b.get("title") else ""
        return f'<div class="description">{title}{inner}</div>'
    raise ValueError(f"unknown block role {role!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("out")
    ap.add_argument("--css")
    ap.add_argument("--title")
    ap.add_argument("--expected", help="also write every text fragment as a JSON list, for validate.py --expected")
    a = ap.parse_args()
    data = json.loads(Path(a.content).read_text())
    if isinstance(data, list):
        data = {"sections": data}
    title = a.title or data.get("title") or "Untitled document"
    lang = data.get("lang", "en-US")
    counter = {"table": 0}
    css = CSS + (Path(a.css).read_text() if a.css else "")
    secs = data["sections"]
    for s in secs:
        s.setdefault("id", f"source-{s['source_page']}" if s.get("source_page") else slug(s["title"]))
    body = '<a class="skip" href="#main">Skip to main content</a><main id="main" tabindex="-1">'
    body += '<div class="cover">'
    if data.get("kicker"):
        body += f"<p>{inline(data['kicker'])}</p>"
    body += f"<h1>{inline(title)}</h1>"
    if data.get("subtitle"):
        body += f"<p>{inline(data['subtitle'])}</p>"
    if data.get("edition_note"):
        body += '<div class="edition-note">' + "".join(f"<p>{inline(p)}</p>" for p in data["edition_note"]) + "</div>"
    body += "</div>"
    if data.get("toc", True):
        body += '<nav aria-label="Contents"><h2>Contents</h2><ul>' + "".join(
            f'<li><a href="#{e(s["id"], True)}">{inline(s["title"])}</a></li>' for s in secs) + "</ul></nav>"
    for s in secs:
        lang_attr = f' lang="{e(s["lang"], True)}"' if s.get("lang") else ""
        body += f'<section id="{e(s["id"], True)}" aria-labelledby="h-{e(s["id"], True)}"{lang_attr}><h2 id="h-{e(s["id"], True)}">{inline(s["title"])}</h2>'
        if data.get("show_source_pages", True) and s.get("source_page"):
            body += f'<p class="source">Source page {e(s["source_page"])}</p>'
        body += "".join(render(b, counter) for b in s["blocks"]) + "</section>"
    body += "</main>"
    if data.get("footer"):
        body += f"<footer><p>{inline(data['footer'])}</p></footer>"
    doc = (f'<!doctype html><html lang="{e(lang, True)}"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
           f"<style>{css}</style></head><body>{body}</body></html>")
    Path(a.out).write_text(doc)
    if a.expected:
        frags = [title]

        def walk(b):
            for k in ("text", "caption", "title", "alt", "name"):
                if isinstance(b.get(k), str):
                    frags.append(LINK.sub(lambda m: m.group(1), b[k]))
            for it in b.get("items", []) + b.get("children", []):
                walk(it) if isinstance(it, dict) else frags.append(LINK.sub(lambda m: m.group(1), it))
            for x in b.get("headers", []) + [v for row in b.get("rows", []) for v in row]:
                frags.append(x)
            for x in b.get("blocks", []) + b.get("groups", []):
                walk(x)
        for s in secs:
            frags.append(s["title"])
            for b in s["blocks"]:
                walk(b)
        Path(a.expected).write_text(json.dumps(frags, ensure_ascii=False, indent=0))
    print(f"wrote {a.out}: {len(secs)} sections, {counter['table']} tables")


if __name__ == "__main__":
    main()
