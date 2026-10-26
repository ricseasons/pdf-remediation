#!/usr/bin/env python3
"""Draft a remediation plan from the audit, leaving judgement calls marked TODO.

Usage: draft_plan.py WORKDIR [--title "..."] [--lang en-US] [--out WORKDIR/plan.draft.json]

Rules applied (each decision carries a "why" so it can be reviewed):
  * Figure that only wraps other tagged text (slide groups, text boxes) → unwrap.
  * Figure that is blank, a thin rule, or page-sized background with no text → artifact.
  * Graphic repeated on 3+ pages (logos, seals, banners) → artifact.
  * Every other Figure → "TODO": look at it in page context and write alt, or artifact it.
  * Largest text on each page (≥1.25× body size) → heading candidate, listed under "_heading_candidates".
Everything here is a starting point. Review it against the page renders before applying.
"""
import argparse
import re
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdfa11y import write_json  # noqa: E402


# Auto-generated or meaningless alt text that must be rewritten.
WEAK_ALT = (r"(?i)description automatically generated|ai-generated content|^\s*(image|picture|graphic|photo|logo|icon|"
            r"text|shape|chart|diagram|figure|placeholder)\s*\d*\s*$|\.(png|jpe?g|gif|emf|wmf)\b|^\s*$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--title")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--out")
    a = ap.parse_args()
    work = Path(a.workdir)
    S = json.loads((work / "audit" / "structure.json").read_text())
    inv = json.loads((work / "audit" / "inventory.json").read_text())
    groups = json.loads((work / "figures" / "groups.json").read_text())
    by_id = {r["id"]: r for r in S}
    kids = defaultdict(list)
    for r in S:
        if r["parent"]:
            kids[r["parent"]].append(r["id"])

    def text_desc(i):
        out = []
        for k in kids[i]:
            if by_id[k]["text"]:
                out.append(k)
            out.extend(text_desc(k))
        return out

    group_of = {i: g for g in groups for i in g["ids"]}
    elements = {}
    todo = []
    for r in S:
        if r["std"] not in ("/Figure", "/Formula"):
            continue
        g = group_of.get(r["id"], {})
        pw = 612 * 792  # nominal; only used for "page-sized"
        bb = r["bbox"]
        area = (bb[2] - bb[0]) * (bb[3] - bb[1]) if bb else 0
        nested_text = text_desc(r["id"])
        if nested_text and not r["mcids"]:
            elements[str(r["id"])] = {"unwrap": True, "alt": None, "why": f"container for {len(nested_text)} tagged text elements"}
        elif nested_text and not r["text"]:
            elements[str(r["id"])] = {"strip_graphics": True, "unwrap": True, "alt": None,
                                      "why": f"shape behind {len(nested_text)} tagged text elements"}
        elif nested_text:
            elements[str(r["id"])] = {"role": "Div", "alt": None,
                                      "why": "TODO graphic with its own text plus nested text: decide alt vs. unwrap"}
            todo.append(r["id"])
        elif g.get("blank") or not bb:
            elements[str(r["id"])] = {"artifact": True, "why": "no visible content"}
        elif bb and (bb[2] - bb[0] < 3 or bb[3] - bb[1] < 3):
            elements[str(r["id"])] = {"artifact": True, "why": "thin rule"}
        elif area > 0.6 * pw and not r["subtree_text"]:
            elements[str(r["id"])] = {"artifact": True, "why": "page-sized background: TODO confirm no information"}
            todo.append(r["id"])
        elif len(g.get("pages", [])) >= 3:
            elements[str(r["id"])] = {"artifact": True, "why": f"repeated graphic on pages {g['pages']}"}
        else:
            weak = bool(r["alt"]) and bool(re.search(WEAK_ALT, r["alt"]))
            elements[str(r["id"])] = {"alt": "TODO" if weak or not r["alt"] else r["alt"], "why": "TODO judge in context" + (f"; existing alt {r['alt']!r}" if r["alt"] else "")}
            todo.append(r["id"])

    # Repeated page furniture ("Page 3", running headers) becomes pagination artifacts.
    import re
    for r in S:
        if r["std"] == "/P" and re.fullmatch(r"(?i)page\s*\d+(\s*of\s*\d+)?", r["text"].strip() or "x"):
            elements[str(r["id"])] = {"artifact": True, "why": "page number"}

    # Heading candidates by font size.
    sizes = [s for r in S for s in r["sizes"] if r["text"]]
    body = statistics.median(sizes) if sizes else 11
    cands = []
    for r in S:
        if r["text"] and r["sizes"] and max(r["sizes"]) >= 1.25 * body and len(r["text"]) < 160:
            cands.append({"id": r["id"], "page": r["page"], "size": max(r["sizes"]), "text": r["text"][:120], "current": r["role"]})
    plan = {
        "metadata": {"title": a.title or "TODO descriptive document title", "lang": a.lang or inv.get("lang") or "en-US"},
        "elements": elements,
        "unwrap_roles": [],
        "merge": [],
        "order": {},
        "lists": [],
        "new": [],
        "tables": {},
        "_body_font_size": body,
        "_heading_candidates": cands,
        "_todo_figures": todo,
    }
    out = Path(a.out) if a.out else work / "plan.draft.json"
    write_json(out, plan)
    counts = defaultdict(int)
    for v in elements.values():
        counts["unwrap" if v.get("unwrap") else "artifact" if v.get("artifact") else "div" if v.get("role") == "Div" else "alt"] += 1
    print(f"wrote {out}: {dict(counts)}; {len(todo)} figures need judgement; {len(cands)} heading candidates (body {body}pt)")


if __name__ == "__main__":
    main()
