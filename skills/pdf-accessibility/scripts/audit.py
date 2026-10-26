#!/usr/bin/env python3
"""Inventory a PDF for accessibility remediation.

Usage: audit.py INPUT.pdf WORKDIR [--dpi 110] [--no-verapdf]

Writes into WORKDIR/audit/:
  inventory.json   document- and page-level facts (tagging, metadata, fonts, scan signals)
  structure.json   every structure element with role, text, bbox, alt, page
  tree-NN.txt      readable per-page tag tree (objnum role [mcids] text | alt)
  figures.json     Figure/Formula elements with bbox and nested text (input to figure_sheets.py)
  links.json       link annotations, rects, targets, whether tagged
  untagged.json    text that is neither tagged nor an artifact
  verapdf.json     veraPDF PDF/UA-1 summary (if veraPDF is installed)
  AUDIT.md         human summary and repair-vs-rebuild signals
and WORKDIR/pages/page-NN.png renders for visual review.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pikepdf  # noqa: E402
from pdfa11y import Doc, page_objects_by_mcid, run_verapdf, union_bbox, write_json, HEADING_RE  # noqa: E402


def render_pages(pdf_path, outdir, dpi):
    import pymupdf as fitz
    outdir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc):
        page.get_pixmap(dpi=dpi).save(str(outdir / f"page-{i + 1:02}.png"))
    return len(doc)


def scan_signals(pdf_path):
    """Per page: text chars, image area fraction, and whether text is likely image-only."""
    import pymupdf as fitz
    doc = fitz.open(str(pdf_path))
    out = []
    for i, page in enumerate(doc):
        area = page.rect.width * page.rect.height
        img_area = 0.0
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            img_area += max(0, x1 - x0) * max(0, y1 - y0)
        text = page.get_text("text")
        out.append({"page": i + 1, "chars": len(text.strip()), "image_fraction": round(min(1.0, img_area / area), 3),
                    "images": len(page.get_images()),
                    "likely_image_text": len(text.strip()) < 200 and img_area / area > 0.25})
    return out


def fonts_inventory(pdf):
    fonts = {}
    for i, page in enumerate(pdf.pages):
        res = page.obj.get("/Resources", {})
        for name, f in res.get("/Font", {}).items():
            key = f.objgen
            if key in fonts:
                continue
            desc = f.get("/FontDescriptor")
            if desc is None and "/DescendantFonts" in f:
                desc = f.DescendantFonts[0].get("/FontDescriptor")
            embedded = bool(desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")))
            fonts[key] = {"name": str(f.get("/BaseFont", name)), "subtype": str(f.get("/Subtype")),
                          "embedded": embedded or str(f.get("/Subtype")) == "/Type3",
                          "tounicode": "/ToUnicode" in f, "first_page": i + 1}
    return list(fonts.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("workdir")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--no-verapdf", action="store_true")
    a = ap.parse_args()
    work = Path(a.workdir)
    out = work / "audit"
    out.mkdir(parents=True, exist_ok=True)

    d = Doc(a.input)
    pdf = d.pdf
    root = pdf.Root
    mc, untagged = page_objects_by_mcid(a.input)

    # ---- structure ----
    elems = []
    roles = Counter()
    per_page = defaultdict(list)
    traced = False
    if d.tree is not None:
        first = next(d.walk(), None)
        traced = first is not None and str(first[0].get("/ID", "")).startswith("src-")
        for e, parent, depth, pg in d.walk():
            refs = d.content_refs(e, pg)
            mcids = [(r[1], r[2]) for r in refs if r[0] == "mcid"]
            texts = [mc.get(m, {}).get("text", "") for m in mcids]
            sub = [(r[1], r[2]) for r in d.subtree_refs(e, pg) if r[0] == "mcid"]
            bbox = union_bbox([mc.get(m, {}).get("bbox") for m in sub])
            def pid(x):
                xs = str(x.get("/ID", ""))
                return int(xs[4:]) if xs.startswith("src-") else (f"out-{x.objgen[0]}" if traced else x.objgen[0])
            sid = str(e.get("/ID", ""))
            rec = {
                "id": int(sid[4:]) if sid.startswith("src-") else (f"out-{e.objgen[0]}" if traced else e.objgen[0]), "role": str(e.S), "std": d.role(e), "depth": depth,
                "page": (pg + 1) if pg is not None else None,
                "parent": (pid(parent) if parent is not None else None),
                "mcids": [m[1] for m in mcids],
                "objr": sum(1 for r in refs if r[0] == "objr"),
                "text": " ".join(t for t in texts if t),
                "subtree_text": " ".join(mc.get(m, {}).get("text", "") for m in sub if mc.get(m, {}).get("text"))[:600],
                "alt": str(e.get("/Alt", "")) or None, "actualtext": str(e.get("/ActualText", "")) or None,
                "lang": str(e.get("/Lang", "")) or None,
                "bbox": [round(v, 1) for v in bbox] if bbox else None,
                "kinds": sorted({k for m in sub for k in mc.get(m, {}).get("kinds", [])}),
                "sizes": sorted({s for m in mcids for s in mc.get(m, {}).get("sizes", [])}),
                "images": sorted({n for m in sub for n in mc.get(m, {}).get("images", []) if n}),
                "children": sum(1 for k in pikepdf.Array(e.K) if isinstance(k, pikepdf.Dictionary) and "/S" in k)
                if isinstance(e.get("/K"), pikepdf.Array) else (1 if isinstance(e.get("/K"), pikepdf.Dictionary) and "/S" in e.K else 0),
            }
            elems.append(rec)
            roles[rec["std"]] += 1
            if rec["page"]:
                per_page[rec["page"]].append(rec)
    write_json(out / "structure.json", elems)
    for pg, recs in per_page.items():
        lines = []
        for r in recs:
            info = re.sub(r"\s+", " ", r["text"])[:160]
            if r["alt"]:
                info += f" | ALT={re.sub(r'\s+', ' ', r['alt'])[:160]}"
            if r["actualtext"]:
                info += f" | ACTUAL={r['actualtext'][:120]}"
            bb = r["bbox"] and "bbox=" + ",".join(f"{v:.0f}" for v in r["bbox"])
            lines.append(f"{'  ' * r['depth']}{r['id']} {r['role']}{'→' + r['std'] if r['std'] != r['role'] else ''}"
                         f" {r['mcids'] or ''} {bb or ''} {info}".rstrip())
        (out / f"tree-{pg:02}.txt").write_text("\n".join(lines))

    figures = [r for r in elems if r["std"] in ("/Figure", "/Formula")]
    write_json(out / "figures.json", figures)

    # ---- annotations ----
    tagged_annots = set()
    for e, _, _, pg in d.walk():
        for r in d.content_refs(e, pg):
            if r[0] == "objr":
                tagged_annots.add(r[2].objgen)
    links = []
    for i, page in enumerate(pdf.pages):
        for an in page.obj.get("/Annots", []):
            sub = str(an.get("/Subtype"))
            act = an.get("/A", {})
            links.append({"page": i + 1, "subtype": sub, "rect": [round(float(v), 1) for v in an.Rect],
                          "uri": str(act.get("/URI", "")) or None, "dest": str(an.get("/Dest", "")) or None,
                          "action": str(act.get("/S", "")) or None, "contents": str(an.get("/Contents", "")) or None,
                          "tagged": an.objgen in tagged_annots, "struct_parent": int(an.StructParent) if "/StructParent" in an else None})
    write_json(out / "links.json", links)
    write_json(out / "untagged.json", untagged)

    # ---- document facts ----
    info = {str(k): str(v) for k, v in pdf.docinfo.items()} if pdf.docinfo else {}
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        xmp_title = meta.get("dc:title")
        pdfua = meta.get("pdfuaid:part")
    signals = scan_signals(a.input)
    headings = [(r["std"], r["text"] or r["subtree_text"][:80]) for r in elems if HEADING_RE.match(r["std"]) or r["std"] == "/H"]
    inv = {
        "file": str(Path(a.input).resolve()), "pages": len(pdf.pages), "pdf_version": pdf.pdf_version,
        "encrypted": pdf.is_encrypted, "tagged": d.tree is not None,
        "marked": bool(root.get("/MarkInfo", {}).get("/Marked", False)),
        "lang": str(root.get("/Lang", "")) or None, "info": info, "xmp_title": xmp_title, "pdfua_part": pdfua,
        "display_doc_title": bool(root.get("/ViewerPreferences", {}).get("/DisplayDocTitle", False)),
        "outlines": "/Outlines" in root, "acroform_fields": len(root.get("/AcroForm", {}).get("/Fields", [])),
        "optional_content": "/OCProperties" in root, "rolemap": d.rolemap, "role_counts": dict(roles),
        "figures": len(figures), "figures_without_alt": sum(1 for f in figures if not f["alt"] and not f["actualtext"]),
        "headings": headings, "links": len(links), "untagged_links": sum(1 for l in links if l["subtype"] == "/Link" and not l["tagged"]),
        "untagged_text_runs": len(untagged), "fonts": fonts_inventory(pdf), "pages_detail": signals,
        "tabs": [str(p.obj.get("/Tabs", "")) for p in pdf.pages],
    }
    write_json(out / "inventory.json", inv)

    n = render_pages(a.input, work / "pages", a.dpi)
    vera = None if a.no_verapdf else run_verapdf(a.input)
    if vera:
        write_json(out / "verapdf.json", vera)

    # ---- summary ----
    md = [f"# Accessibility audit: {Path(a.input).name}", ""]
    md.append(f"- Pages: {n}; PDF {inv['pdf_version']}; tagged: {inv['tagged']}; lang: {inv['lang']}; "
              f"title: {info.get('/Title')!r}; DisplayDocTitle: {inv['display_doc_title']}; PDF/UA id: {pdfua}")
    md.append(f"- Structure roles: {dict(roles.most_common())}")
    md.append(f"- Figures: {len(figures)} ({inv['figures_without_alt']} without Alt/ActualText)")
    md.append(f"- Headings found: {len(headings)}; links: {len(links)} ({inv['untagged_links']} untagged)")
    md.append(f"- Untagged text runs: {len(untagged)}; fonts not embedded: "
              f"{[f['name'] for f in inv['fonts'] if not f['embedded']]}; fonts without ToUnicode: "
              f"{[f['name'] for f in inv['fonts'] if not f['tounicode'] and f['subtype'] != '/Type3']}")
    img_pages = [s["page"] for s in signals if s["likely_image_text"]]
    md.append(f"- Pages that look image-only (OCR needed): {img_pages or 'none'}")
    if vera:
        md.append(f"- veraPDF {vera.get('version')} PDF/UA-1: compliant={vera['compliant']}; rules failed {vera['rules_failed']}, "
                  f"checks failed {vera['checks_failed']}")
        for f in vera["failures"]:
            md.append(f"  - {f['clause']}-{f['test']} x{f['failed_checks']}: {f['description'][:140]}")
    md += ["", "## Signals for repair vs rebuild", ""]
    if not inv["tagged"]:
        md.append("- Untagged source: repair needs full auto-tagging; prefer **rebuild** unless layout fidelity is mandatory.")
    if img_pages:
        md.append(f"- Image-of-text on pages {img_pages}: WCAG 1.4.5 needs real text. Rebuild those pages, or OCR and provide alt/ActualText as an interim.")
    wrappers = roles.get("/Art", 0) + roles.get("/Div", 0)
    if wrappers > n * 5:
        md.append(f"- {wrappers} Art/Div wrappers (typical of slide exports): repair plan should unwrap them and set reading order.")
    if inv["figures"] > n * 8:
        md.append(f"- {inv['figures']} figures: most are probably decorative shapes. Use figure_sheets.py and classify.")
    if not headings:
        md.append("- No headings: assign H1/H2… from visual titles (see page renders).")
    (out / "AUDIT.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
