#!/usr/bin/env python3
"""Local OCR of page images, positioned in PDF coordinates.

Usage: ocr.py INPUT.pdf WORKDIR --pages 7,8,9 [--dpi 300] [--lang eng] [--psm 3]
       [--engine auto|tesseract|vision] [--vision-lang en-US]
       [--region PAGE:x0,top,x1,bottom]   (crop before OCR; repeatable)

Engines run on this machine only. tesseract works everywhere; vision (Apple Vision via
ocr_vision.swift, macOS only) is usually better on small slide print. auto picks vision
when swift is available on macOS, otherwise tesseract. Vision has no layout blocks, so
lines are grouped into blocks by column and spacing.

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
import platform
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


def ocr_vision(png, langs):
    """Apple Vision lines as (text, conf, [x0, top, x1, bottom]) in pixels."""
    swift = shutil.which("swift")
    if not swift:
        sys.exit("swift not found; install Xcode command line tools or use --engine tesseract")
    script = Path(__file__).with_name("ocr_vision.swift")
    res = subprocess.run([swift, str(script), str(png), *langs], capture_output=True, text=True)
    if res.returncode:
        sys.exit("Vision OCR failed (check OS permissions, or use --engine tesseract):\n" + res.stderr)
    return [(r["text"], r["conf"], r["box"]) for r in json.loads(res.stdout)]


def vision_blocks(lines):
    """Group Vision lines into blocks: same column (x overlap) and a small vertical gap."""
    lines = sorted(lines, key=lambda l: (l[2][1], l[2][0]))
    blocks = []                                           # [last box, [indices]]
    out = [None] * len(lines)
    for i, (_, _, b) in enumerate(lines):
        h = b[3] - b[1]
        for blk in reversed(blocks):
            lb = blk[0]
            overlap = min(b[2], lb[2]) - max(b[0], lb[0])
            if overlap > 0.3 * min(b[2] - b[0], lb[2] - lb[0]) and 0 <= b[1] - lb[3] < 1.2 * h:
                blk[0] = b
                out[i] = blocks.index(blk)
                break
        else:
            blocks.append([b])
            out[i] = len(blocks) - 1
    return lines, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("workdir")
    ap.add_argument("--pages", required=True, help="comma list, 1-based")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--psm", type=int, default=3)
    ap.add_argument("--region", action="append", default=[])
    ap.add_argument("--engine", choices=["auto", "tesseract", "vision"], default="auto")
    ap.add_argument("--vision-lang", default="en-US", help="comma list of BCP 47 tags for Vision")
    a = ap.parse_args()
    engine = a.engine
    if engine == "auto":
        engine = "vision" if platform.system() == "Darwin" and shutil.which("swift") else "tesseract"
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
            if engine == "vision":
                vl, blk = vision_blocks(ocr_vision(png, a.vision_lang.split(",")))
                for (text, conf, (vx0, vt, vx1, vb)), bi in zip(vl, blk):
                    lines.append({"id": f"p{pg}-l{len(lines) + 1}", "block": f"r{ri}v{bi}", "text": text,
                                  "conf": round(conf, 1),
                                  "bbox": [round(vx0 / scale + x0, 1), round(vt / scale + t, 1),
                                           round(vx1 / scale + x0, 1), round(vb / scale + t, 1)]})
                continue
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
        (out / f"page-{pg:02}.json").write_text(json.dumps({"page": pg, "dpi": a.dpi, "engine": engine, "lines": lines}, indent=1, ensure_ascii=False))
        (out / f"page-{pg:02}.txt").write_text("\n".join(
            f"{l['id']} c{l['conf']:.0f} {','.join(f'{v:.0f}' for v in l['bbox'])} {l['text']}" for l in lines))
        low = sum(1 for l in lines if l["conf"] < 70)
        print(f"page {pg} ({engine}): {len(lines)} lines ({low} below 70% confidence) → {out / f'page-{pg:02}.txt'}")


if __name__ == "__main__":
    main()
