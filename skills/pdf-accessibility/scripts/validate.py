#!/usr/bin/env python3
"""Validate a remediated PDF: machine checks plus evidence for the human review.

Usage: validate.py OUTPUT.pdf OUTDIR [--source SOURCE.pdf] [--profiles ua1,ua2] [--expected texts.json]
                                       [--contrast] [--max-pages-contrast 60]

Checks (each reported as pass / fail / review with evidence):
  pdfua.<profile>     veraPDF PDF/UA-1 (Matterhorn machine-checkable conditions) and optionally PDF/UA-2
  metadata            title present and not generic, DisplayDocTitle, Lang, PDF/UA identifier, MarkInfo
  headings            exactly one H1, no skipped levels, headings not empty
  figures             every Figure has Alt/ActualText; flags generic or auto-generated alt and very long alt
  links               every Link annotation tagged with Contents; flags non-descriptive link text
  tables              header cells present, scopes set, rows regular
  lists               L > LI > (Lbl) LBody shape
  empty               structure elements with no content
  untagged            visible text that is neither tagged nor an artifact
  visual_diff         (with --source) per-page pixel difference: layout-preserving repair should be 0
  coverage            (with --source or --expected) source text missing from the tagged reading order
  contrast            (with --contrast) estimated text contrast against the rendered background (WCAG 1.4.3)
  tab_order           pages with annotations use /Tabs /S
Writes OUTDIR/validation.json, OUTDIR/VALIDATION.md and OUTDIR/screenreader.txt.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pikepdf import Dictionary, Name  # noqa: E402
from pdfa11y import Doc, fonts_inventory, is_elem, norm_text, page_objects_by_mcid, run_verapdf, seq, write_json  # noqa: E402

GENERIC_TITLE = re.compile(r"(?i)^\s*(powerpoint presentation|microsoft word.*|untitled.*|document\d*|slide \d+|\S+\.(docx?|pptx?|pdf))\s*$")
WEAK_ALT = re.compile(r"(?i)description automatically generated|ai-generated content|^\s*(image|picture|graphic|photo|logo|icon|"
                      r"text|shape|chart|diagram|figure|placeholder|todo)\s*\d*\s*$|\.(png|jpe?g|gif|emf|wmf)\b")
WEAK_LINK = re.compile(r"(?i)^\s*(click here|here|link|this link|more|read more|this|https?://\S+)\s*$")


def check(name, status, detail, evidence=None):
    return {"check": name, "status": status, "detail": detail, "evidence": evidence or []}


def structure_checks(d: Doc, mc):
    results = []
    root = d.pdf.Root
    title = str(d.pdf.docinfo.get("/Title", "")) if d.pdf.docinfo else ""
    with d.pdf.open_metadata(set_pikepdf_as_editor=False) as m:
        xmp_title = m.get("dc:title")
        ua = m.get("pdfuaid:part")
    problems = []
    if not title or GENERIC_TITLE.match(title):
        problems.append(f"title {title!r} missing or generic")
    if not xmp_title:
        problems.append("XMP dc:title missing")
    if not bool(root.get("/ViewerPreferences", {}).get("/DisplayDocTitle", False)):
        problems.append("DisplayDocTitle not true")
    if not str(root.get("/Lang", "")):
        problems.append("document /Lang missing")
    if not ua:
        problems.append("PDF/UA identifier missing")
    if not bool(root.get("/MarkInfo", {}).get("/Marked", False)):
        problems.append("MarkInfo/Marked not true")
    soft = [f"{k[1:].lower()} missing" for k in ("/Author", "/Subject")
            if not (d.pdf.docinfo and str(d.pdf.docinfo.get(k, "")).strip())]
    results.append(check("metadata", "fail" if problems else ("review" if soft else "pass"),
                         "; ".join(problems + soft) or f"title {title!r}, lang {root.get('/Lang')}, PDF/UA-{ua}"))
    loose = [f for f in fonts_inventory(d.pdf) if not f["embedded"]]
    results.append(check("fonts", "review" if loose else "pass",
                         f"{len(loose)} font(s) not embedded" + (" (allowed by PDF/UA-1 only for invisible text; "
                         "Section 508 checkers flag them)" if loose else ""), [f"{f['name']} p{f['first_page']}" for f in loose]))
    if d.tree is None:
        results.append(check("tagged", "fail", "document has no structure tree"))
        return results

    def text_of(e, pg):
        pg = d.page_of(e, pg)
        if "/ActualText" in e:
            return str(e.ActualText)
        out = []
        for k in seq(e.get("/K")):
            if isinstance(k, int):
                out.append(mc.get((pg, k), {}).get("text", ""))
            elif isinstance(k, Dictionary) and k.get("/Type") == Name.MCR:
                kp = d.page_index.get(k.Pg.objgen, pg) if "/Pg" in k else pg
                out.append(mc.get((kp, int(k.MCID)), {}).get("text", ""))
            elif is_elem(k):
                out.append(text_of(k, pg))
        return re.sub(r"\s+", " ", " ".join(x for x in out if x)).strip()

    levels, empty_h, figs, weak, long_alt, no_alt, empties, lists_bad = [], [], 0, [], [], [], [], []
    tables, links = [], []
    for e, parent, depth, pg in d.walk():
        r = d.role(e)
        m = re.match(r"^/H([1-6])$", r)
        if m:
            tx = text_of(e, pg)
            levels.append((int(m.group(1)), tx[:80], (pg or 0) + 1))
            if not tx:
                empty_h.append(f"p{(pg or 0) + 1} {r}")
        if r in ("/Figure", "/Formula"):
            figs += 1
            a = str(e.get("/Alt", "")) or str(e.get("/ActualText", ""))
            if not a.strip():
                no_alt.append(f"p{(pg or 0) + 1} obj {e.objgen[0]}")
            elif WEAK_ALT.search(a):
                weak.append(f"p{(pg or 0) + 1}: {a[:80]!r}")
            elif len(a) > 1500:
                long_alt.append(f"p{(pg or 0) + 1}: {len(a)} chars")
        if r == "/LI":
            ks = [k for k in seq(e.get("/K")) if is_elem(k)]
            if not ks or any(d.role(k) not in ("/Lbl", "/LBody") for k in ks):
                lists_bad.append(f"p{(pg or 0) + 1} LI obj {e.objgen[0]}")
        if r == "/Table":
            tables.append((e, pg))
        if r == "/Link":
            links.append((e, pg))
        if r not in ("/TD", "/TH", "/TR", "/Document", "/Table", "/Figure") and not seq(e.get("/K")) and "/ActualText" not in e and "/Alt" not in e:
            empties.append(f"p{(pg or 0) + 1} {r} obj {e.objgen[0]}")

    h1 = sum(1 for lv, _, _ in levels if lv == 1)
    skips = []
    prev = 0
    for lv, tx, p in levels:
        if lv > prev + 1:
            skips.append(f"p{p} H{prev}→H{lv} {tx!r}")
        prev = lv
    hs = "pass"
    detail = f"{len(levels)} headings ({Counter(f'H{lv}' for lv, _, _ in levels)}), {h1} H1"
    if not levels or h1 != 1 or skips or empty_h:
        hs = "fail" if (not levels or empty_h) else "review"
    results.append(check("headings", hs, detail + (f"; skipped levels {len(skips)}" if skips else ""), skips + empty_h))
    results.append(check("figures", "fail" if no_alt else ("review" if weak or long_alt else "pass"),
                         f"{figs} figures; {len(no_alt)} without alt; {len(weak)} weak alt; {len(long_alt)} very long",
                         no_alt + weak + long_alt))
    results.append(check("lists", "fail" if lists_bad else "pass", f"{len(lists_bad)} malformed list items", lists_bad[:30]))
    results.append(check("empty", "review" if empties else "pass", f"{len(empties)} empty structure elements", empties[:30]))

    # tables
    tproblems = []
    for t, pg in tables:
        rows = []

        def collect(x):
            for k in seq(x.get("/K")):
                if is_elem(k):
                    rr = d.role(k)
                    if rr == "/TR":
                        rows.append(k)
                    elif rr in ("/THead", "/TBody", "/TFoot"):
                        collect(k)
        collect(t)
        ths = [c for r_ in rows for c in seq(r_.get("/K")) if is_elem(c) and d.role(c) == "/TH"]
        if not ths:
            tproblems.append(f"p{(pg or 0) + 1} table obj {t.objgen[0]} has no TH")
        for c in ths:
            scope = None
            for a in seq(c.get("/A")):
                if isinstance(a, Dictionary) and "/Scope" in a:
                    scope = a.Scope
            if scope is None:
                tproblems.append(f"p{(pg or 0) + 1} TH without Scope")
                break
    results.append(check("tables", "fail" if any("no TH" in p for p in tproblems) else ("review" if tproblems else "pass"),
                         f"{len(tables)} tables", tproblems))

    # links
    tagged_annots = {}
    for e, pg in links:
        for k in seq(e.get("/K")):
            if isinstance(k, Dictionary) and k.get("/Type") == Name.OBJR:
                tagged_annots[k.Obj.objgen] = text_of(e, pg)
    lproblems = []
    nlinks = 0
    for i, page in enumerate(d.pdf.pages):
        for an in page.obj.get("/Annots", []):
            if an.get("/Subtype") != Name.Link:
                continue
            nlinks += 1
            if an.objgen not in tagged_annots:
                lproblems.append(f"p{i + 1} untagged link")
            if not str(an.get("/Contents", "")).strip():
                lproblems.append(f"p{i + 1} link without Contents")
            tx = tagged_annots.get(an.objgen, "")
            if tx and WEAK_LINK.match(tx):
                lproblems.append(f"p{i + 1} non-descriptive link text {tx!r} (check context, WCAG 2.4.4)")
    results.append(check("links", "fail" if any("untagged" in p or "without" in p for p in lproblems) else ("review" if lproblems else "pass"),
                         f"{nlinks} link annotations", lproblems))
    tabs = [i + 1 for i, p in enumerate(d.pdf.pages) if p.obj.get("/Annots") and p.obj.get("/Tabs") != Name.S]
    results.append(check("tab_order", "fail" if tabs else "pass", f"pages with annotations lacking /Tabs /S: {tabs or 'none'}"))
    return results


def visual_diff(src, out, dpi=50):
    import pymupdf as fitz
    from PIL import Image, ImageChops
    a, b = fitz.open(str(src)), fitz.open(str(out))
    if len(a) != len(b):
        return check("visual_diff", "review", f"page count changed {len(a)} → {len(b)} (expected for a rebuilt edition)")
    diffs = []
    for i in range(len(a)):
        pa, pb = a[i].get_pixmap(dpi=dpi), b[i].get_pixmap(dpi=dpi)
        ia = Image.frombytes("RGB", (pa.width, pa.height), pa.samples)
        ib = Image.frombytes("RGB", (pb.width, pb.height), pb.samples)
        if ia.size != ib.size:
            diffs.append(f"p{i + 1} size changed")
            continue
        dd = ImageChops.difference(ia, ib).convert("L")
        n = sum(1 for v in dd.tobytes() if v > 30)
        if n:
            diffs.append(f"p{i + 1}: {n} pixels differ")
    return check("visual_diff", "fail" if diffs else "pass",
                 f"{len(a)} pages compared at {dpi} dpi; {'identical rendering' if not diffs else str(len(diffs)) + ' pages differ'}", diffs)


def tagged_text(path):
    out = subprocess.run([sys.executable, str(Path(__file__).with_name("screenreader.py")), str(path), "--max-text", "100000"],
                         capture_output=True, text=True)
    return out.stdout


def coverage(src, out_transcript, expected=None):
    """Which source text fragments are absent from the output's tagged reading order?"""
    import pdfplumber
    target = norm_text(out_transcript)
    frags = []
    if expected:
        frags = [x for x in json.loads(Path(expected).read_text()) if len(norm_text(x)) >= 4]
    else:
        smc, suntagged = page_objects_by_mcid(src)
        if smc:
            # tagged source: compare per marked-content run, which keeps columns apart
            for (pg, _), v in sorted(smc.items()):
                if len(norm_text(v["text"])) >= 8:
                    frags.append((pg + 1, v["text"]))
        for u in suntagged:
            frags.append((u["page"] + 1, u["text"]))
        if not frags:
            with pdfplumber.open(str(src)) as pdf:
                for i, p in enumerate(pdf.pages):
                    for line in (p.extract_text(x_tolerance=1.5) or "").splitlines():
                        if len(norm_text(line)) >= 12:
                            frags.append((i + 1, line.strip()))
    missing = []
    for f in frags:
        pg, tx = f if isinstance(f, tuple) else (None, f)
        if norm_text(tx) not in target:
            missing.append(f"{'p' + str(pg) + ': ' if pg else ''}{tx[:100]}")
    status = "pass" if not missing else "review"
    return check("coverage", status, f"{len(frags) - len(missing)}/{len(frags)} source text runs found in the tagged reading order "
                 "(missing runs are usually deliberate artifacts: confirm each)",
                 missing[:200])


def contrast(path, max_pages=60):
    """Estimate text/background contrast from the rendering. Approximate: gradients and images fool it."""
    import pymupdf as fitz

    def lum(c):
        c = [v / 255 for v in c]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        la, lb = sorted((lum(a), lum(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)

    doc = fitz.open(str(path))
    low = []
    n = 0
    for pi, page in enumerate(doc):
        if pi >= max_pages:
            break
        pix = page.get_pixmap(dpi=96)
        sx, sy = pix.width / page.rect.width, pix.height / page.rect.height
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s.get("alpha", 255) == 0 or not s["text"].strip():
                        continue
                    n += 1
                    col = s["color"]
                    fg = ((col >> 16) & 255, (col >> 8) & 255, col & 255)
                    x0, y0, x1, y1 = s["bbox"]
                    px = []
                    for yy in range(int(y0 * sy), min(pix.height, int(y1 * sy) + 1), 2):
                        for xx in range(int(x0 * sx), min(pix.width, int(x1 * sx) + 1), 2):
                            px.append(tuple(pix.pixel(xx, yy)[:3]))
                    if not px:
                        continue
                    if not any(sum(abs(p[i] - fg[i]) for i in range(3)) < 48 for p in px):
                        continue  # text colour not rendered here: hidden or covered text (check separately)
                    far = [p for p in px if sum(abs(p[i] - fg[i]) for i in range(3)) > 60]
                    if not far:
                        continue
                    bg = Counter(far).most_common(1)[0][0]
                    r = ratio(fg, bg)
                    large = s["size"] >= 18 or (s["size"] >= 14 and "bold" in s["font"].lower())
                    need = 3.0 if large else 4.5
                    if r < need:
                        low.append(f"p{pi + 1} {r:.2f}:1 (needs {need}) {s['text'][:50]!r} fg={fg} bg={bg}")
    return check("contrast", "review" if low else "pass", f"{n} text spans sampled; {len(low)} below WCAG 1.4.3 thresholds (estimate)", low[:100])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--source")
    ap.add_argument("--profiles", default="ua1")
    ap.add_argument("--expected", help="JSON list of text fragments that must appear in the reading order")
    ap.add_argument("--contrast", action="store_true")
    ap.add_argument("--max-pages-contrast", type=int, default=60)
    ap.add_argument("--no-visual-diff", action="store_true")
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    vera_full = {}
    for prof in a.profiles.split(","):
        v = run_verapdf(a.pdf, prof)
        if v is None:
            results.append(check(f"pdfua.{prof}", "review", "veraPDF not installed; run scripts/setup.sh"))
            continue
        vera_full[prof] = v
        st = "pass" if v.get("compliant") else "fail"
        results.append(check(f"pdfua.{prof}", st, f"veraPDF {v.get('version')}: {v['rules_passed']} rules passed, {v['rules_failed']} failed; "
                             f"{v['checks_passed']} checks passed, {v['checks_failed']} failed",
                             [f"{f['clause']}-{f['test']} ×{f['failed_checks']}: {f['description'][:160]}" for f in v["failures"]]))
    d = Doc(a.pdf)
    mc, untagged = page_objects_by_mcid(a.pdf)
    results += structure_checks(d, mc)
    results.append(check("untagged", "fail" if untagged else "pass", f"{len(untagged)} untagged, non-artifact text runs",
                         [f"p{u['page'] + 1}: {u['text'][:80]!r}" for u in untagged[:30]]))
    transcript = tagged_text(a.pdf)
    (out / "screenreader.txt").write_text(transcript)
    if a.source and not a.no_visual_diff:
        results.append(visual_diff(a.source, a.pdf))
    if a.source or a.expected:
        results.append(coverage(a.source, transcript, a.expected))
    if a.contrast:
        results.append(contrast(a.pdf, a.max_pages_contrast))
    write_json(out / "validation.json", {"file": str(Path(a.pdf).resolve()), "results": results, "verapdf": vera_full})
    icon = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}
    md = [f"# Validation: {Path(a.pdf).name}", "", "| Check | Result | Detail |", "|---|---|---|"]
    for r in results:
        md.append(f"| {r['check']} | {icon[r['status']]} | {r['detail']} |")
    for r in results:
        if r["evidence"]:
            md += ["", f"### {r['check']} ({icon[r['status']]})", ""] + [f"- {e}" for e in r["evidence"][:60]]
            if len(r["evidence"]) > 60:
                md.append(f"- … {len(r['evidence']) - 60} more in validation.json")
    md += ["", "Automated checks cannot establish WCAG conformance on their own. Complete the manual review in",
           "references/manual-review.md (screen reader read-through, reflow/zoom, alt-text accuracy, owner sign-off)."]
    (out / "VALIDATION.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:4 + len(results)]))
    sys.exit(1 if any(r["status"] == "fail" for r in results) else 0)


if __name__ == "__main__":
    main()
