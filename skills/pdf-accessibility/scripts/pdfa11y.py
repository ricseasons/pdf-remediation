"""Shared helpers for the pdf-accessibility skill.

Everything here runs locally. No function in this module sends document
content over the network.

Structure elements are addressed by their PDF object number ("objnum"), which
is stable for the life of a file as long as it is saved with pikepdf
(object streams preserved, no renumbering). The audit, plan and repair steps
must therefore all run against the same input file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name

HEADING_RE = re.compile(r"^/H([1-6])$")
# Standard structure types from ISO 32000-1 14.8.4 (PDF/UA-1 baseline).
STANDARD_TYPES = {
    "/Document", "/Part", "/Art", "/Sect", "/Div", "/BlockQuote", "/Caption", "/TOC", "/TOCI",
    "/Index", "/NonStruct", "/Private", "/P", "/H", "/H1", "/H2", "/H3", "/H4", "/H5", "/H6",
    "/L", "/LI", "/Lbl", "/LBody", "/Table", "/TR", "/TH", "/TD", "/THead", "/TBody", "/TFoot",
    "/Span", "/Quote", "/Note", "/Reference", "/BibEntry", "/Code", "/Link", "/Annot", "/Ruby",
    "/RB", "/RT", "/RP", "/Warichu", "/WT", "/WP", "/Figure", "/Formula", "/Form",
}


def seq(v):
    """Normalise a /K value (or anything) to a Python list."""
    if v is None:
        return []
    if isinstance(v, Array):
        return list(v)
    return [v]


def objnum(o) -> int | None:
    try:
        n = o.objgen[0]
        return n or None
    except Exception:
        return None


def is_elem(o) -> bool:
    return isinstance(o, Dictionary) and "/S" in o and o.get("/Type", Name.StructElem) == Name.StructElem


class Doc:
    """A PDF opened for accessibility work: pikepdf handle plus tree helpers."""

    def __init__(self, path: str | Path, allow_overwriting_input=False):
        self.path = Path(path)
        self.pdf = pikepdf.open(str(path), allow_overwriting_input=allow_overwriting_input)
        self.page_index = {p.obj.objgen: i for i, p in enumerate(self.pdf.pages)}
        root = self.pdf.Root
        self.tree = root.get("/StructTreeRoot")
        self.rolemap = {}
        if self.tree is not None and "/RoleMap" in self.tree:
            self.rolemap = {str(k): str(v) for k, v in self.tree.RoleMap.items()}

    # ---- roles -------------------------------------------------------
    def std_role(self, role: str) -> str:
        """Resolve a custom role through the RoleMap to a standard type."""
        seen = set()
        while role not in STANDARD_TYPES and role in self.rolemap and role not in seen:
            seen.add(role)
            role = self.rolemap[role]
        return role

    def role(self, e) -> str:
        return self.std_role(str(e.S))

    # ---- traversal ---------------------------------------------------
    def page_of(self, e, inherited=None):
        if isinstance(e, Dictionary) and "/Pg" in e:
            return self.page_index.get(e.Pg.objgen, inherited)
        return inherited

    def walk(self, start=None):
        """Yield (elem, parent, depth, page) depth-first in logical order."""
        if self.tree is None:
            return
        stack = [(k, None, 0, None) for k in reversed(seq(self.tree.get("/K")) if start is None else [start])]
        while stack:
            e, parent, depth, pg = stack.pop()
            if not is_elem(e):
                continue
            pg = self.page_of(e, pg)
            yield e, parent, depth, pg
            for k in reversed(seq(e.get("/K"))):
                if is_elem(k):
                    stack.append((k, e, depth + 1, pg))

    def content_refs(self, e, pg=None):
        """Direct marked-content and object references of one element.

        Returns a list of ('mcid', page, mcid, stream_or_None) and
        ('objr', page, obj) tuples, in /K order.
        """
        pg = self.page_of(e, pg)
        out = []
        for k in seq(e.get("/K")):
            if isinstance(k, int):
                out.append(("mcid", pg, int(k), None))
            elif isinstance(k, Dictionary):
                t = k.get("/Type")
                if t == Name.MCR:
                    kp = self.page_index.get(k.Pg.objgen, pg) if "/Pg" in k else pg
                    out.append(("mcid", kp, int(k.MCID), k.get("/Stm")))
                elif t == Name.OBJR:
                    kp = self.page_index.get(k.Pg.objgen, pg) if "/Pg" in k else pg
                    out.append(("objr", kp, k.Obj))
        return out

    def subtree_refs(self, e, pg=None):
        pg = self.page_of(e, pg)
        refs = list(self.content_refs(e, pg))
        for k in seq(e.get("/K")):
            if is_elem(k):
                refs.extend(self.subtree_refs(k, pg))
        return refs

    # ---- parent tree -------------------------------------------------
    def parent_tree(self):
        if self.tree is None or "/ParentTree" not in self.tree:
            return None
        return pikepdf.NumberTree(self.tree.ParentTree)

    def next_parent_key(self):
        nt = self.parent_tree()
        keys = [int(k) for k, _ in nt.items()] if nt is not None else []
        n = max(keys) + 1 if keys else 0
        if self.tree is not None and "/ParentTreeNextKey" in self.tree:
            n = max(n, int(self.tree.ParentTreeNextKey))
        return n

    def save(self, out):
        self.pdf.save(str(out), object_stream_mode=pikepdf.ObjectStreamMode.preserve)


# ---- page content ------------------------------------------------------

def page_objects_by_mcid(pdf_path: str | Path):
    """Use pdfplumber to collect text/graphics per (page, mcid).

    Returns {(page, mcid): {"text": str, "bbox": [x0, top, x1, bottom], "kinds": set,
    "colors": [...], "sizes": [...]}} plus a list of untagged text per page.
    """
    import pdfplumber
    from pdfplumber.utils import extract_text

    out = {}
    untagged = []
    kp = pikepdf.open(str(pdf_path))
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, p in enumerate(pdf.pages):
            vec = vector_mcid_bboxes(kp, i)
            for mcid, bb in vec.items():
                out[(i, mcid)] = {"text": "", "bbox": bb, "kinds": ["vector"], "tag": None, "sizes": [], "fonts": [], "images": []}
            groups = defaultdict(list)
            for kind in ("chars", "images", "rects", "curves", "lines"):
                for o in getattr(p, kind):
                    groups[o.get("mcid")].append(o)
            for mcid, objs in groups.items():
                chars = [o for o in objs if o["object_type"] == "char"]
                if mcid is None:
                    chars = [c for c in chars if c.get("tag") != "Artifact"]
                    if chars:
                        t = extract_text(chars, x_tolerance=1.5, y_tolerance=3).strip()
                        if t:
                            untagged.append({"page": i, "text": t})
                    continue
                text = extract_text(chars, x_tolerance=1.5, y_tolerance=3) if chars else ""
                prior = out.get((i, mcid))
                out[(i, mcid)] = {
                    "text": re.sub(r"[ \t]+", " ", text).strip(),
                    "bbox": [min(o["x0"] for o in objs), min(o["top"] for o in objs),
                             max(o["x1"] for o in objs), max(o["bottom"] for o in objs)],
                    "kinds": sorted({o["object_type"] for o in objs}),
                    "tag": objs[0].get("tag"),
                    "sizes": sorted({round(c["size"], 1) for c in chars}),
                    "fonts": sorted({c["fontname"] for c in chars}),
                    "images": [o.get("name") for o in objs if o["object_type"] == "image"],
                }
                if prior:
                    out[(i, mcid)]["bbox"] = union_bbox([prior["bbox"], out[(i, mcid)]["bbox"]])
                    out[(i, mcid)]["kinds"].append("vector")
    return out, untagged


def _mul(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def vector_mcid_bboxes(pdf, page_index):
    """Bounding boxes of path/image/shading content per MCID, from the content stream.

    pdfplumber misses clip-plus-shading drawings (gradient outlined text is a
    common case), so this interpreter tracks the CTM and collects path points
    and image unit squares inside each marked-content sequence. Coordinates
    are returned top-based like pdfplumber: [x0, top, x1, bottom].
    """
    page = pdf.pages[page_index]
    h = float(page.mediabox[3])
    res = page.obj.get("/Resources", {})
    ctm = (1, 0, 0, 1, 0, 0)
    stack = []
    mc = []  # stack of mcid or None
    pts = defaultdict(list)
    path = []   # points of the path under construction (device space)
    clip = []   # last clipping path, used to size shadings ("sh")

    def cur_mcid():
        return next((m for m in reversed(mc) if m is not None), None)

    def tx(x, y):
        a, b, c, d, e, f = ctm
        return (a * x + c * y + e, b * x + d * y + f)

    def commit(points):
        m = cur_mcid()
        if m is not None:
            pts[m].extend(points)

    try:
        ops = pikepdf.parse_content_stream(page)
    except Exception:
        return {}
    pending_clip = False
    for ci in ops:
        o = str(ci.operator)
        v = ci.operands
        if o == "q":
            stack.append((ctm, clip))
        elif o == "Q":
            if stack:
                ctm, clip = stack.pop()
        elif o == "cm":
            ctm = _mul(tuple(float(x) for x in v), ctm)
        elif o in ("BDC", "BMC"):
            mid = None
            if o == "BDC" and len(v) > 1:
                props = v[1]
                if isinstance(props, Name):
                    props = res.get("/Properties", {}).get(props)
                if isinstance(props, Dictionary) and "/MCID" in props:
                    mid = int(props.MCID)
            mc.append(mid)
        elif o == "EMC":
            if mc:
                mc.pop()
        elif o in ("m", "l"):
            path.append(tx(float(v[0]), float(v[1])))
        elif o == "c":
            path.extend(tx(float(v[i]), float(v[i + 1])) for i in range(0, 6, 2))
        elif o in ("v", "y"):
            path.extend(tx(float(v[i]), float(v[i + 1])) for i in range(0, 4, 2))
        elif o == "re":
            x, y, w, hh = (float(t) for t in v)
            path.extend(tx(px, py) for px, py in ((x, y), (x + w, y), (x, y + hh), (x + w, y + hh)))
        elif o in ("W", "W*"):
            pending_clip = True
        elif o in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s"):
            commit(path)
            if pending_clip:
                clip = list(path)
            path, pending_clip = [], False
        elif o == "n":
            if pending_clip:
                clip = list(path)
            path, pending_clip = [], False
        elif o == "sh":
            commit(clip)
        elif o in ("Do", "BI", "INLINE IMAGE"):
            sq = [tx(px, py) for px, py in ((0, 0), (1, 0), (0, 1), (1, 1))]
            if clip:
                cx = [p[0] for p in clip]
                cy = [p[1] for p in clip]
                sq = [(min(max(x, min(cx)), max(cx)), min(max(y, min(cy)), max(cy))) for x, y in sq]
            commit(sq)
    out = {}
    for k, p in pts.items():
        if not p:
            continue
        xs = [max(-1, min(x, 10000)) for x, _ in p]
        ys = [y for _, y in p]
        out[k] = [min(xs), h - max(ys), max(xs), h - min(ys)]
    return out


def union_bbox(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ---- external tools ----------------------------------------------------

def verapdf_bin():
    for name in ("verapdf",):
        p = shutil.which(name)
        if p:
            return p
    import os
    cache = Path(os.environ.get("PDF_A11Y_CACHE", Path.home() / ".cache" / "pdf-a11y"))
    for p in (cache / "verapdf" / "verapdf", Path.home() / "verapdf" / "verapdf", Path("/opt/verapdf/verapdf")):
        if p.exists():
            return str(p)
    return None


def run_verapdf(pdf: str | Path, flavour="ua1", max_failed_per_rule=20):
    """Run veraPDF locally and return a compact summary dict, or None if absent."""
    exe = verapdf_bin()
    if not exe:
        return None
    cmd = [exe, "-f", flavour, "--format", "json", "--maxfailuresdisplayed", str(max_failed_per_rule), str(pdf)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    raw = res.stdout[res.stdout.find("{"):] if "{" in res.stdout else ""
    if not raw:
        return {"error": (res.stderr or res.stdout)[-2000:]}
    data = json.loads(raw)
    summary = {"profile": flavour, "rules_passed": 0, "rules_failed": 0, "checks_passed": 0, "checks_failed": 0,
               "compliant": None, "failures": [], "version": None}
    try:
        summary["version"] = data["report"]["buildInformation"]["releaseDetails"][0]["version"]
    except Exception:
        pass

    def find(o):
        if isinstance(o, dict):
            if "validationResult" in o:
                vr = o["validationResult"]
                vr = vr[0] if isinstance(vr, list) else vr
                summary["compliant"] = vr.get("compliant")
                d = vr.get("details", {})
                summary.update(rules_passed=d.get("passedRules", 0), rules_failed=d.get("failedRules", 0),
                               checks_passed=d.get("passedChecks", 0), checks_failed=d.get("failedChecks", 0))
                for r in d.get("ruleSummaries", []):
                    if r.get("ruleStatus") == "FAILED" or r.get("failedChecks"):
                        summary["failures"].append({
                            "clause": r.get("clause"), "test": r.get("testNumber"),
                            "failed_checks": r.get("failedChecks"), "description": r.get("description"),
                            "contexts": [c.get("context") for c in r.get("checks", [])][:max_failed_per_rule],
                        })
                return True
            return any(find(v) for v in o.values())
        if isinstance(o, list):
            return any(find(v) for v in o)
        return False

    find(data)
    return summary


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
