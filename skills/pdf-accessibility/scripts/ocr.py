#!/usr/bin/env python3
"""Local OCR of page images with Tesseract, positioned in PDF coordinates.

Usage: ocr.py INPUT.pdf WORKDIR --pages 7,8,9 [--dpi 300] [--lang eng] [--psm 3]
       [--region PAGE:x0,top,x1,bottom]   (crop before OCR; repeatable)

Writes WORKDIR/ocr/page-NN.json  {"page", "lines": [{"id", "text", "conf", "bbox"}]}
and   WORKDIR/ocr/page-NN.txt   one line per OCR line: id conf bbox text
Bounding boxes are PDF points, top-based (same convention as audit.py).

OCR output is raw evidence. Before it becomes document text, compare it with
the rendered page (zoom in with a region crop) and correct it: OCR misses
small print, merges columns and drops punctuation. Record corrections in the
plan, not here.
"""
import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz


def ocr_image(png, lang, psm):
    exe = shutil.which("tesseract")
    if not exe:
        sys.exit("tesseract not found; run scripts/setup.sh")
    res = subprocess.run([exe, str(png), "stdout", "-l", lang, "--psm", str(psm), "tsv"], capture_output=True, text=True)
    if res.returncode:
        sys.exit(res.stderr)
    return list(csv.DictReader(io.StringIO(res.stdout), delimiter="\t", quoting=csv.QUOTE_NONE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("workdir")
    ap.add_argument("--pages", required=True, help="comma list, 1-based")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--psm", type=int, default=3)
    ap.add_argument("--region", action="append", default=[])
    a = ap.parse_args()
    out = Path(a.workdir) / "ocr"
    out.mkdir(parents=True, exist_ok=True)
    regions = defaultdict(list)
    for r in a.region:
        pg, box = r.split(":")
        regions[int(pg)].append([float(v) for v in box.split(",")])
    doc = fitz.open(a.input)
    scale = a.dpi / 72
    for pg in [int(p) for p in a.pages.split(",")]:
        page = doc[pg - 1]
        clips = regions.get(pg) or [[0, 0, page.rect.width, page.rect.height]]
        lines = []
        for ri, (x0, t, x1, b) in enumerate(clips):
            png = out / f"page-{pg:02}-r{ri}.png"
            page.get_pixmap(dpi=a.dpi, clip=fitz.Rect(x0, t, x1, b)).save(str(png))
            rows = ocr_image(png, a.lang, a.psm)
            groups = defaultdict(list)
            for row in rows:
                if row.get("level") != "5" or not (row.get("text") or "").strip():
                    continue
                groups[(row["block_num"], row["par_num"], row["line_num"])].append(row)
            for key in sorted(groups, key=lambda k: tuple(int(v) for v in k)):
                ws = groups[key]
                lx0 = min(int(w["left"]) for w in ws) / scale + x0
                lt = min(int(w["top"]) for w in ws) / scale + t
                lx1 = max(int(w["left"]) + int(w["width"]) for w in ws) / scale + x0
                lb = max(int(w["top"]) + int(w["height"]) for w in ws) / scale + t
                conf = sum(float(w["conf"]) for w in ws) / len(ws)
                lines.append({"id": f"p{pg}-l{len(lines) + 1}", "block": f"r{ri}b{key[0]}p{key[1]}",
                              "text": " ".join(w["text"] for w in ws), "conf": round(conf, 1),
                              "bbox": [round(lx0, 1), round(lt, 1), round(lx1, 1), round(lb, 1)]})
        (out / f"page-{pg:02}.json").write_text(json.dumps({"page": pg, "dpi": a.dpi, "lines": lines}, indent=1, ensure_ascii=False))
        (out / f"page-{pg:02}.txt").write_text("\n".join(
            f"{l['id']} c{l['conf']:.0f} {','.join(f'{v:.0f}' for v in l['bbox'])} {l['text']}" for l in lines))
        low = sum(1 for l in lines if l["conf"] < 70)
        print(f"page {pg}: {len(lines)} lines ({low} below 70% confidence) → {out / f'page-{pg:02}.txt'}")


if __name__ == "__main__":
    main()
