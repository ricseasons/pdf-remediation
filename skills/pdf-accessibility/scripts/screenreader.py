#!/usr/bin/env python3
"""Linearize a tagged PDF the way a screen reader would traverse it.

Usage: screenreader.py INPUT.pdf [-o transcript.txt] [--max-text 400]

Prints the structure tree in logical order with roles, heading levels, alt
text, ActualText, list/table shapes and link targets. Read the output top
to bottom as if listening: is everything there, in order, with the right
roles? This is the closest automated stand-in for an NVDA/JAWS read-through;
it does not replace one.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pikepdf import Dictionary, Name  # noqa: E402
from pdfa11y import Doc, is_elem, page_objects_by_mcid, seq  # noqa: E402

CONTAINERS = {"/Document", "/Part", "/Art", "/Sect", "/Div", "/NonStruct", "/Private", "/TOC", "/THead", "/TBody", "/TFoot"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--max-text", type=int, default=400)
    a = ap.parse_args()
    d = Doc(a.input)
    if d.tree is None:
        sys.exit("untagged PDF: a screen reader would fall back to unreliable heuristics")
    mc, _ = page_objects_by_mcid(a.input)
    out = []
    last_page = [None]

    def text_of(e, pg):
        pg = d.page_of(e, pg)
        if "/ActualText" in e:
            return str(e.ActualText)
        parts = []
        for k in seq(e.get("/K")):
            if isinstance(k, int):
                parts.append(mc.get((pg, k), {}).get("text", ""))
            elif isinstance(k, Dictionary) and k.get("/Type") == Name.MCR:
                kp = d.page_index.get(k.Pg.objgen, pg) if "/Pg" in k else pg
                parts.append(mc.get((kp, int(k.MCID)), {}).get("text", ""))
            elif is_elem(k):
                kp = d.page_of(k, pg)
                parts.append(text_of(k, kp))
        return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()

    def clip(t):
        return t if len(t) <= a.max_text else t[: a.max_text] + "…"

    def visit(e, pg, depth):
        pg = d.page_of(e, pg)
        if pg is not None and pg != last_page[0]:
            out.append(f"——— page {pg + 1} ———")
            last_page[0] = pg
        role = d.role(e)
        ind = "  " * depth
        if role in CONTAINERS:
            label = "" if role in ("/Document", "/Sect", "/Div", "/Part", "/Art", "/NonStruct") else f"{ind}[{role[1:]}]"
            if label:
                out.append(label)
            for k in seq(e.get("/K")):
                if is_elem(k):
                    visit(k, pg, depth + (1 if label else 0))
            return
        if role == "/Figure" or role == "/Formula":
            alt = re.sub(r"\s+", " ", str(e.get("/Alt", "")) or str(e.get("/ActualText", ""))).strip()
            out.append(f"{ind}[{role[1:]}] {clip(alt) if alt else '⚠ NO ALT'}")
            return
        if role == "/L":
            items = [k for k in seq(e.get("/K")) if is_elem(k) and d.role(k) == "/LI"]
            out.append(f"{ind}[List, {len(items)} items]")
            for k in seq(e.get("/K")):
                if is_elem(k):
                    visit(k, pg, depth + 1)
            return
        if role == "/LI":
            lbl = [k for k in seq(e.get("/K")) if is_elem(k) and d.role(k) == "/Lbl"]
            body = [k for k in seq(e.get("/K")) if not (is_elem(k) and d.role(k) == "/Lbl")]
            ltxt = " ".join(text_of(k, pg) for k in lbl)
            def own(x):
                # text of a list body without the nested lists it contains
                if "/ActualText" in x:
                    return str(x.ActualText)
                parts = []
                for kk in seq(x.get("/K")):
                    if is_elem(kk):
                        if d.role(kk) != "/L":
                            parts.append(text_of(kk, d.page_of(x, pg)))
                    else:
                        tmp = Dictionary(K=kk)
                        if "/Pg" in x:
                            tmp.Pg = x.Pg
                        parts.append(text_of(tmp, d.page_of(x, pg)))
                return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
            btxt = " ".join(own(k) for k in body if is_elem(k))
            out.append(f"{ind}• {ltxt + ' ' if ltxt else ''}{clip(btxt)}")
            for k in body:
                if is_elem(k):
                    for kk in seq(k.get("/K")):
                        if is_elem(kk) and d.role(kk) == "/L":
                            visit(kk, pg, depth + 1)
            return
        if role == "/Table":
            rows = []

            def collect(x):
                for k in seq(x.get("/K")):
                    if is_elem(k):
                        r = d.role(k)
                        if r == "/TR":
                            rows.append(k)
                        elif r in ("/THead", "/TBody", "/TFoot"):
                            collect(k)
                        elif r == "/Caption":
                            out.append(f"{ind}[Caption] {text_of(k, pg)}")
            collect(e)
            ncols = max((sum(1 for c in seq(r.get("/K")) if is_elem(c)) for r in rows), default=0)
            out.append(f"{ind}[Table, {len(rows)} rows × {ncols} columns]")
            for i, r in enumerate(rows, 1):
                cells = []
                for c in seq(r.get("/K")):
                    if is_elem(c):
                        tag = "TH" if d.role(c) == "/TH" else "TD"
                        t = text_of(c, d.page_of(c, pg))
                        figs = [str(k.get("/Alt", "")) for k in seq(c.get("/K")) if is_elem(k) and d.role(k) == "/Figure"]
                        if figs and not t:
                            t = " ".join(figs)
                        cells.append(f"{tag}:{t or '(empty)'}")
                out.append(f"{ind}  row {i}: " + " | ".join(cells))
            return
        if role == "/Link":
            target = ""
            for k in seq(e.get("/K")):
                if isinstance(k, Dictionary) and k.get("/Type") == Name.OBJR:
                    act = k.Obj.get("/A", {})
                    target = str(act.get("/URI", "")) or ("internal" if ("/Dest" in k.Obj or act.get("/S") == Name.GoTo) else "")
            out.append(f"{ind}[Link{' → ' + target[:80] if target else ''}] {clip(text_of(e, pg))}")
            return
        t = text_of(e, pg)
        m = re.match(r"^/H([1-6])$", role)
        tag = f"H{m.group(1)}" if m else role[1:]
        out.append(f"{ind}[{tag}] {clip(t) if t else '(empty)'}")

    for k in seq(d.tree.get("/K")):
        if is_elem(k):
            visit(k, None, 0)
    text = "\n".join(out) + "\n"
    if a.output:
        Path(a.output).write_text(text)
        print(f"wrote {a.output} ({len(out)} lines)")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
