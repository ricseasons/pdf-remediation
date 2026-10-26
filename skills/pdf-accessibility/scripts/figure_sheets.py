#!/usr/bin/env python3
"""Build labelled contact sheets of every Figure so Claude can classify them visually.

Usage: figure_sheets.py INPUT.pdf WORKDIR [--per-sheet 16] [--dpi 144]

Reads WORKDIR/audit/figures.json (from audit.py). Visually identical crops
(repeated logos, bullets, rules) are grouped so each distinct graphic is
judged once. Writes:
  WORKDIR/figures/sheet-NN.png    labelled crops, 4 columns
  WORKDIR/figures/crops/ID.png    one full-resolution crop per group representative
  WORKDIR/figures/groups.json     [{group, ids, page_list, bbox, size, text, alt, hint}]

Hints are only heuristics (tiny, thin rule, full-page background, contains
text). The decision about decorative vs. meaningful, and the alt text, is a
judgement made by looking at the crop *in its page context*.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from pdfa11y import write_json  # noqa: E402

CELL_W, CELL_H, LABEL_H = 360, 240, 54


def ahash(img, n=12):
    g = img.convert("L").resize((n, n))
    px = list(g.tobytes())
    avg = sum(px) / len(px)
    return "".join("1" if p > avg else "0" for p in px)


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def hint(f, pw, ph):
    if not f["bbox"]:
        return "no visible extent"
    x0, y0, x1, y1 = f["bbox"]
    w, h = x1 - x0, y1 - y0
    if w < 3 or h < 3:
        return "thin rule or dot: likely decorative"
    if w * h > 0.6 * pw * ph:
        return "page-sized: likely background"
    if f["subtree_text"]:
        return "contains real text: alt must cover it, or retag as text"
    if w < 25 and h < 25:
        return "icon-sized"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("workdir")
    ap.add_argument("--per-sheet", type=int, default=16)
    ap.add_argument("--dpi", type=int, default=144)
    ap.add_argument("--pending", help="plan.json: only draw groups whose ids have no decision in it yet")
    a = ap.parse_args()
    work = Path(a.workdir)
    figs = json.loads((work / "audit" / "figures.json").read_text())
    out = work / "figures"
    (out / "crops").mkdir(parents=True, exist_ok=True)
    doc = fitz.open(a.input)
    scale = a.dpi / 72
    pages = {}
    groups = {}
    order = []
    for f in figs:
        if not f["page"]:
            continue
        pg = doc[f["page"] - 1]
        if f["page"] not in pages:
            pages[f["page"]] = pg.get_pixmap(dpi=a.dpi)
        if not f["bbox"]:
            key = f"empty-{f['id']}"
            crop = None
        else:
            x0, y0, x1, y1 = f["bbox"]
            pix = pages[f["page"]]
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            box = (max(0, int(x0 * scale) - 2), max(0, int(y0 * scale) - 2),
                   min(pix.width, int(x1 * scale) + 2), min(pix.height, int(y1 * scale) + 2))
            crop = img.crop(box) if box[2] > box[0] and box[3] > box[1] else None
            key = (ahash(crop) + f"{round((x1 - x0) / 4)}x{round((y1 - y0) / 4)}"
                   + ("|" + f["subtree_text"][:40] if f["subtree_text"] else "")) if crop else f"empty-{f['id']}"
        if key not in groups:
            blank = True
            if crop:
                lo, hi = crop.convert("L").getextrema()
                blank = hi - lo < 12
            groups[key] = {"group": len(groups) + 1, "blank": blank or not crop, "ids": [], "pages": [], "bbox": f["bbox"], "text": f["subtree_text"][:300],
                           "alt": f["alt"], "hint": hint(f, pg.rect.width, pg.rect.height), "crop": crop, "rep": f["id"]}
            order.append(key)
        g = groups[key]
        g["ids"].append(f["id"])
        if f["page"] not in g["pages"]:
            g["pages"].append(f["page"])
        if f["alt"] and not g["alt"]:
            g["alt"] = f["alt"]

    lab = font(13)
    reps = [groups[k] for k in order]
    write_json(out / "groups.json", [{k: v for k, v in g.items() if k != "crop"} for g in reps])
    prefix = "sheet"
    if a.pending:
        decided = set(json.loads(Path(a.pending).read_text()).get("elements", {}))
        reps = [g for g in reps if str(g["rep"]) not in decided]
        prefix = "pending"
        for old in out.glob("pending-*.png"):
            old.unlink()
    for s in range(0, len(reps), a.per_sheet):
        chunk = reps[s:s + a.per_sheet]
        cols = 4
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * CELL_W, rows * (CELL_H + LABEL_H)), "white")
        dr = ImageDraw.Draw(sheet)
        for i, g in enumerate(chunk):
            cx, cy = (i % cols) * CELL_W, (i // cols) * (CELL_H + LABEL_H)
            dr.rectangle([cx + 2, cy + 2, cx + CELL_W - 3, cy + CELL_H - 3], outline="#bbbbbb")
            # checkerboard-free grey backing makes white-on-white shapes visible
            dr.rectangle([cx + 3, cy + 3, cx + CELL_W - 4, cy + CELL_H - 4], fill="#e8e8e8")
            if g["crop"]:
                c = g["crop"].copy()
                c.thumbnail((CELL_W - 12, CELL_H - 12))
                sheet.paste(c, (cx + (CELL_W - c.width) // 2, cy + (CELL_H - c.height) // 2))
            ids = g["ids"]
            label = f"G{g['group']} id {g['rep']}" + (f" (+{len(ids) - 1} same)" if len(ids) > 1 else "") + f" p{','.join(map(str, g['pages'][:6]))}"
            dr.text((cx + 6, cy + CELL_H + 2), label, fill="black", font=lab)
            sub = ("ALT: " + g["alt"][:44]) if g["alt"] else (g["hint"] or "")
            dr.text((cx + 6, cy + CELL_H + 20), sub[:52], fill="#444444", font=lab)
            if g["crop"]:
                g["crop"].save(out / "crops" / f"{g['rep']}.png")
        sheet.save(out / f"{prefix}-{s // a.per_sheet + 1:02}.png")
    print(f"{len(figs)} figures in {len(groups)} visual groups; drew {len(reps)} groups on "
          f"{(len(reps) + a.per_sheet - 1) // a.per_sheet} {prefix} sheets in {out}")


if __name__ == "__main__":
    main()
