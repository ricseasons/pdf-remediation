"""Example: scripting a repair plan for a slide-export report.

This is a condensed, anonymised version of the plan builder used on a 22-page
PowerPoint-exported operational plan (414 figures, 467 TextBox wrappers, no
headings, image-of-text pages, milestone "tables" made of loose text boxes).
Element ids, names and alt text below are illustrative; the patterns are the point:

  1. start from draft_plan.py's mechanical decisions
  2. hand-written decisions for one-off pages (cover, contents, diagrams)
  3. OCR alignment: known-good text + Tesseract line boxes → invisible text layers
  4. a geometric builder for pages that share a template
  5. colour-only meaning put into words

Every alt text and role here was decided by looking at the page renders first.
Run: python3 build_plan_example.py WORK  → WORK/plan.json
"""
import difflib
import json
import re
import sys
from pathlib import Path

W = Path(sys.argv[1] if len(sys.argv) > 1 else "WORK")
S = json.loads((W / "audit/structure.json").read_text())
by = {r["id"]: r for r in S}
kids = {}
for r in S:
    kids.setdefault(r["parent"], []).append(r["id"])

plan = json.loads((W / "plan.draft.json").read_text())          # 1. mechanical decisions
for k in [k for k in plan if k.startswith("_")]:
    del plan[k]
E = plan["elements"]
plan["metadata"] = {"title": "Office FY 2027 Operational Plan", "lang": "en-US"}
plan["unwrap_roles"] = ["TextBox", "Group"]                     # slide wrappers add nothing
order, lists, merge, tables = plan["order"], plan["lists"], plan["merge"], plan["tables"]
layers = plan.setdefault("text_layers", [])


def t(i):
    return re.sub(r"\s+", " ", by[i]["text"]).strip()


def art(*ids, why="decorative"):
    for i in ids:
        E[str(i)] = {"artifact": True, "why": why}


def alt(i, text):
    E[str(i)] = {"alt": text}


def role(i, r, actual=None):
    e = {k: v for k, v in E.get(str(i), {}).items() if k not in ("artifact", "unwrap", "strip_graphics")}
    e["role"] = r
    if actual:                        # e.g. outlined/vector heading, or letter-spaced "O P E R A T I O N A L"
        e["actualtext"], e["alt"] = actual, None
    E[str(i)] = e


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Repeated furniture on every page: tagline banner and "Page N".
for r in S:
    if r["std"] == "/P" and re.fullmatch(r"(?i)page \d+|p\s*l\s*a\s*n.*i\s*n\s*f\s*o\s*r\s*m", t(r["id"]) or "x"):
        art(r["id"], why="page furniture")

# ---------------------------------------------------------------- 2. one-off pages
# Cover: two-line office name becomes one paragraph; big title + letter-spaced subtitle is the H1.
merge += [[101, 102], [103, 104]]
role(103, "H1", "FY 2027 Operational Plan")
art(100, why="cover photograph")
alt(105, "Bureau name")                                 # publisher logo, first occurrence only
order["99"] = [101, 103, 105]

# Contents page: TOC/TOCI roles, vector heading gets ActualText.
role(201, "H2", "Table of Contents")
role(202, "TOC")
for i in (203, 204, 205):
    role(i, "TOCI")

# A diagram that carries real information: alt with its structure, in order.
alt(301, "Diagram: a continuous cycle of Plan, Execute, Monitor and Inform around the strategic vision; "
         "four functional areas, each listing its functions: …")

# Hidden text under an image that conflicts with what is visible: artifact it AND report it.
art(302, why="superseded chart text hidden beneath the visible chart image (owner to confirm)")


# ---------------------------------------------------------------- 3. OCR text layers
def ocr_lines(pg):
    return json.loads((W / f"ocr/page-{pg:02}.json").read_text())["lines"]


def align(texts, lines):
    """Find each corrected block text among the OCR lines (any column), for positioning only."""
    out, used = [], set()
    for tx in texts:
        target, best = norm(tx), (0, 0, 1)
        for s in range(len(lines)):
            acc = ""
            for e in range(s, min(s + 40, len(lines))):
                if e in used or lines[e]["block"] != lines[s]["block"]:
                    break
                acc += norm(lines[e]["text"])
                if len(acc) > len(target) * 1.4 + 10:
                    break
                sm = difflib.SequenceMatcher(None, target, acc, autojunk=False)
                if sm.quick_ratio() > best[0] and sm.ratio() > best[0]:
                    best = (sm.ratio(), s, e + 1)
        r, s, e = best
        if r < 0.75:
            print(f"check OCR position for {tx[:50]!r} ({r:.2f})", file=sys.stderr)
        used.update(range(s, e))
        out.append([l["id"] for l in lines[s:e]])
    return out


# Text comes from a corrected transcription (proofread against the zoomed render), never raw OCR.
corrected = [("H3", "Strategic & Operational Planning"), ("P", "Define the future, establish priorities, …")]
ids = align([tx for _, tx in corrected], ocr_lines(7))
art(700, why="image of text, replaced by the tagged text layer below")
layers.append({"page": 7, "parent": 699, "after": 701,
               "blocks": [{"role": r, "text": tx, "ocr": li} for (r, tx), li in zip(corrected, ids)]})

# ---------------------------------------------------------------- 4. template pages by geometry
SECTIONS = ["DESCRIPTION", "OPPORTUNITY", "RISKS & CHALLENGES", "STRATEGIC ALIGNMENT", "MILESTONES", "PERFORMANCE EVALUATION"]


def descendants(i):
    out = []
    for k in kids.get(i, []):
        out += [k] + descendants(k)
    return out


def center(r):
    return (r["bbox"][1] + r["bbox"][3]) / 2


for slide_id in (1200, 1300):                        # one Sect per template page
    ps = [by[i] for i in descendants(slide_id) if by[i]["std"] == "/P" and by[i]["text"].strip()]
    heads = {t(r["id"]): r for r in ps if t(r["id"]) in SECTIONS}
    for h in heads.values():
        role(h["id"], "H3")

    def owner(r):                                    # nearest section heading above, same column
        col = [h for h in heads.values() if (h["bbox"][0] < 260) == (r["bbox"][0] < 255) and h["bbox"][1] <= r["bbox"][1] + 1]
        return t(max(col, key=lambda h: h["bbox"][1])["id"]) if col else None

    groups = {k: [] for k in heads}
    for r in ps:
        if r["id"] not in {h["id"] for h in heads.values()} and owner(r):
            groups[owner(r)].append(r)
    o = []
    for name in [s for s in SECTIONS if s in heads]:
        o.append(heads[name]["id"])
        members = sorted(groups[name], key=lambda r: (r["bbox"][1], r["bbox"][0]))
        if name in ("OPPORTUNITY", "RISKS & CHALLENGES"):
            # bullet glyphs are separate text boxes: pair each with the text below it, keep the glyph as Lbl
            bullets = [r for r in members if t(r["id"]) == "•"]
            texts = [r for r in members if t(r["id"]) != "•"]
            items = []
            for bi, b in enumerate(bullets):
                nxt = bullets[bi + 1]["bbox"][1] if bi + 1 < len(bullets) else 1e9
                items.append({"lbl": b["id"], "body": [r["id"] for r in texts if b["bbox"][1] - 4 <= r["bbox"][1] < nxt - 4]})
            lists.append({"name": f"{slide_id}-{name[:4]}", "items": items})
            o.append(f"{slide_id}-{name[:4]}")
        elif name == "MILESTONES":
            # number | description | target quarter, scattered boxes → ordered list item per row
            nums = [r for r in members if re.fullmatch(r"\d{1,2}", t(r["id"]))]
            tgts = [r for r in members if re.fullmatch(r"FY \d{4} Q\d|TBD", t(r["id"]))]
            descs = [r for r in members if r not in nums and r not in tgts]
            items = [{"lbl": n["id"], "body": [min(descs, key=lambda r: abs(center(r) - center(n)))["id"],
                                               min(tgts, key=lambda r: abs(center(r) - center(n)))["id"]]}
                     for n in sorted(nums, key=lambda r: int(t(r["id"])))]
            lists.append({"name": f"{slide_id}-ms", "items": items, "ordered": True})
            o.append(f"{slide_id}-ms")
        else:
            o += [r["id"] for r in members]
    order[str(slide_id)] = o

# ---------------------------------------------------------------- 5. colour-only meaning in words
# A row of goal labels where navy shading = aligned and grey = not aligned: state it for AT,
# and list the visual-only cue as an owner issue (WCAG 1.4.1).
for pid, state in ((1251, "aligned"), (1252, "not aligned")):
    role(pid, "P", f"{t(pid)}: {state}")

# Icons that are the only content of a table cell: move them into the cell and name them.
tables["1400"] = {"header_rows": 1, "header_cols": 1, "place": [[1, 2, [1401]]]}
alt(1401, "Aligned")

(W / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
print("wrote", W / "plan.json")
