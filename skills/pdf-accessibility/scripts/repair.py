#!/usr/bin/env python3
"""Layout-preserving remediation: apply a remediation plan to an existing tagged PDF.

Usage: repair.py INPUT.pdf PLAN.json OUTPUT.pdf [--workdir WORKDIR] [--report OUT.json]

INPUT must be the same file audit.py inspected (element ids are object numbers).
The plan is written by Claude after looking at the page renders, tag trees and
figure sheets; see references/repair-plan.md for the full schema. Automatic
fixes (metadata, PDF/UA identifier, link tagging, annotation descriptions,
table regularity, tab order, optional-content names, CIDSet) run on every
invocation and can be disabled with "auto": {"<fix>": false} in the plan.

Order of operations:
  1. merges, new grouping elements           4. role/alt/actualtext/lang edits ("elements")
  2. reordering / reparenting ("order")       5. unwrap
  3. figure groups expanded into elements      6. artifact (content stream rewrite) and empty-element pruning
  7. automatic fixes                           8. save, verify the tree still parses
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pikepdf  # noqa: E402
from pikepdf import Array, Dictionary, Name, String  # noqa: E402
from pdfa11y import Doc, is_elem, seq, write_json  # noqa: E402

LOG = []


def log(msg):
    LOG.append(msg)


class Repair:
    def __init__(self, doc: Doc, plan: dict, workdir: Path | None):
        self.d = doc
        self.pdf = doc.pdf
        self.plan = plan
        self.workdir = workdir
        self.by_id = {}
        self.named = {}
        for e, parent, _, _ in doc.walk():
            self.by_id[e.objgen[0]] = e
            if parent is not None and "/P" not in e:
                e.P = parent
        self.root_elem = doc.tree
        self.pt = doc.parent_tree()

    # ---- addressing -------------------------------------------------
    def get(self, ref):
        if isinstance(ref, str) and not ref.isdigit():
            if ref in self.named:
                return self.named[ref]
            raise KeyError(f"unknown element name {ref!r}")
        e = self.by_id.get(int(ref))
        if e is None:
            raise KeyError(f"element {ref} not found in structure tree")
        return e

    def parent(self, e):
        return e.get("/P")

    def kids(self, e):
        return seq(e.get("/K"))

    def set_kids(self, e, kids):
        if not kids:
            if "/K" in e:
                del e["/K"]
        else:
            e.K = Array(kids)

    def page_ref(self, e):
        while e is not None and isinstance(e, Dictionary):
            if "/Pg" in e:
                return e.Pg
            e = e.get("/P")
        return None

    def detach(self, e):
        p = self.parent(e)
        if p is None:
            return
        ks = [k for k in self.kids(p) if not (isinstance(k, Dictionary) and k.is_indirect and k.objgen == e.objgen)]
        self.set_kids(p, ks)

    def index_in_parent(self, e):
        p = self.parent(e)
        for i, k in enumerate(self.kids(p)):
            if isinstance(k, Dictionary) and k.is_indirect and k.objgen == e.objgen:
                return i
        return None

    def explicit_mcrs(self, e):
        """Rewrite bare integer MCIDs as MCR dicts carrying /Pg so they survive moves."""
        pg = self.page_ref(e)
        out = []
        for k in self.kids(e):
            if isinstance(k, int) and pg is not None:
                out.append(Dictionary(Type=Name.MCR, Pg=pg, MCID=k))
            else:
                out.append(k)
        if out:
            self.set_kids(e, out)

    def new_elem(self, role, parent, name=None, extra=None):
        ne = self.pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name("/" + role.lstrip("/")), P=parent))
        if extra:
            for k, v in extra.items():
                ne[k] = v
        self.by_id[ne.objgen[0]] = ne
        if name:
            self.named[name] = ne
        return ne

    def move_into(self, child, new_parent, position=None):
        if self.page_ref(child) is not None and "/Pg" not in child:
            child.Pg = self.page_ref(child)
        self.explicit_mcrs(child)
        self.detach(child)
        child.P = new_parent
        ks = self.kids(new_parent)
        if position is None:
            ks.append(child)
        else:
            ks.insert(position, child)
        self.set_kids(new_parent, ks)

    # ---- parent tree ------------------------------------------------
    def retarget_parent_tree(self, refs, new_owner):
        """Point ParentTree entries for MCIDs/OBJRs at a new owning element (or None)."""
        if self.pt is None:
            return
        for r in refs:
            if r[0] == "mcid":
                _, pgi, mcid, stm = r
                holder = stm if stm is not None else self.pdf.pages[pgi].obj
                if "/StructParents" not in holder:
                    continue
                key = int(holder.StructParents)
                arr = self.pt.get(key)
                if arr is None or not isinstance(arr, Array) or mcid >= len(arr):
                    continue
                arr[mcid] = new_owner if new_owner is not None else pikepdf.Object.parse(b"null")
            elif r[0] == "objr":
                obj = r[2]
                if "/StructParent" in obj and new_owner is not None:
                    self.pt[int(obj.StructParent)] = new_owner

    # ---- 1. grouping -------------------------------------------------
    def apply_new(self):
        for spec in self.plan.get("new", []):
            children = [self.get(c) for c in spec.get("children", [])]
            parent = self.get(spec["parent"]) if "parent" in spec else self.parent(children[0])
            pos = self.index_in_parent(children[0]) if children and self.parent(children[0]) is parent else None
            ne = self.new_elem(spec["role"], parent, spec.get("name"))
            ks = self.kids(parent)
            ks.insert(pos if pos is not None else len(ks), ne)
            self.set_kids(parent, ks)
            for c in children:
                self.move_into(c, ne)
            for k in ("alt", "actualtext", "lang", "title"):
                if k in spec:
                    ne[{"alt": "/Alt", "actualtext": "/ActualText", "lang": "/Lang", "title": "/T"}[k]] = String(spec[k])
            log(f"new {spec['role']} {spec.get('name', ne.objgen[0])} with {len(children)} children")
        for spec in self.plan.get("lists", []):
            items = [self.get((c.get("lbl") or c["body"][0]) if isinstance(c, dict) else c) for c in spec["items"]]
            parent = self.get(spec["parent"]) if "parent" in spec else self.parent(items[0])
            pos = self.index_in_parent(items[0]) if self.parent(items[0]) is parent else None
            lst = self.new_elem("L", parent, spec.get("name"))
            if spec.get("ordered"):
                lst.A = Dictionary(O=Name.List, ListNumbering=Name.Decimal)
            elif spec.get("numbering"):
                lst.A = Dictionary(O=Name.List, ListNumbering=Name("/" + spec["numbering"]))
            ks = self.kids(parent)
            ks.insert(pos if pos is not None else len(ks), lst)
            self.set_kids(parent, ks)
            for spec_it, it in zip(spec["items"], items):
                li = self.new_elem("LI", lst)
                self.set_kids(lst, self.kids(lst) + [li])
                if isinstance(spec_it, dict) and spec_it.get("lbl") is not None:
                    lbl = self.get(spec_it["lbl"])
                    self.move_into(lbl, li)
                    lbl.S = Name.Lbl
                body = self.new_elem("LBody", li)
                self.set_kids(li, self.kids(li) + [body])
                for b in (spec_it.get("body", []) if isinstance(spec_it, dict) else [spec_it]):
                    self.move_into(self.get(b), body)
            log(f"list {spec.get('name', lst.objgen[0])} with {len(items)} items")

    # ---- 1b. merge ----------------------------------------------------
    def apply_merge(self):
        """Join elements split by layout (a paragraph broken across columns, a two-line title)."""
        for ids in self.plan.get("merge", []):
            els = [self.get(i) for i in ids]
            first = els[0]
            self.explicit_mcrs(first)
            ks = self.kids(first)
            for e in els[1:]:
                self.explicit_mcrs(e)
                pg = self.page_ref(e)
                refs = self.d.content_refs(e, self.d.page_index.get(pg.objgen) if pg is not None else None)
                moved = self.kids(e)
                for k in moved:
                    if is_elem(k):
                        k.P = first
                ks.extend(moved)
                self.retarget_parent_tree(refs, first)
                self.detach(e)
                self.by_id.pop(e.objgen[0], None)
            self.set_kids(first, ks)
        if self.plan.get("merge"):
            log(f"merged {len(self.plan['merge'])} split elements")

    # ---- 2. order ----------------------------------------------------
    def apply_order(self):
        for pid, order in self.plan.get("order", {}).items():
            parent = self.get(pid)
            listed = [c for c in order if c != "*"]
            listed_elems = [self.get(c) for c in listed]
            for c in listed_elems:
                if self.parent(c) is not None and self.parent(c).objgen != parent.objgen:
                    self.move_into(c, parent)
            ids = {c.objgen for c in listed_elems}
            remaining = [k for k in self.kids(parent) if not (isinstance(k, Dictionary) and k.is_indirect and k.objgen in ids)]
            new = []
            for c in order:
                if c == "*":
                    new.extend(remaining)
                else:
                    new.append(self.get(c))
            if "*" not in order:
                new.extend(remaining)
            self.set_kids(parent, new)
            log(f"order {pid}: {len(listed)} placed")

    # ---- 3/4. element edits -----------------------------------------
    def expand_groups(self):
        groups = self.plan.get("figure_groups", {})
        if not groups:
            return
        gfile = self.workdir / "figures" / "groups.json" if self.workdir else None
        if not gfile or not gfile.exists():
            raise SystemExit("figure_groups in plan needs --workdir with figures/groups.json")
        index = {str(g["group"]): g for g in json.loads(gfile.read_text())}
        els = self.plan.setdefault("elements", {})
        for gid, spec in groups.items():
            g = index[str(gid).lstrip("G")]
            for i in g["ids"]:
                els.setdefault(str(i), dict(spec))

    def apply_elements(self):
        remap = {("/" + k.lstrip("/")): ("/" + v.lstrip("/")) for k, v in self.plan.get("retag_roles", {}).items()}
        if remap:
            n = 0
            for e in self.by_id.values():
                if str(e.S) in remap:
                    e.S = Name(remap[str(e.S)])
                    n += 1
            log(f"retagged {n} elements by role map {remap}")
        for eid, spec in self.plan.get("elements", {}).items():
            try:
                e = self.get(eid)
            except KeyError as ex:
                if not spec.get("why"):  # draft-generated entries for merged-away elements are expected
                    log(f"WARNING {ex}")
                continue
            if "role" in spec:
                e.S = Name("/" + spec["role"].lstrip("/"))
            for key, pdfkey in (("alt", "/Alt"), ("actualtext", "/ActualText"), ("lang", "/Lang"), ("expansion", "/E"), ("title", "/T")):
                if key in spec:
                    if spec[key] in (None, ""):
                        if pdfkey in e:
                            del e[pdfkey]
                    else:
                        e[pdfkey] = String(spec[key])
            if "attributes" in spec:
                e.A = Dictionary({("/" + k.lstrip("/")): (Name("/" + v.lstrip("/")) if isinstance(v, str) and v.startswith("/") else v)
                                  for k, v in spec["attributes"].items()})
            if "scope" in spec:
                set_attr(e, "/Table", "/Scope", Name("/" + spec["scope"]))

    # ---- 3b. invisible text layers (OCR / outlined text) -------------
    def apply_text_layers(self):
        """Add invisible (Tr 3) tagged text over image-of-text or outlined-text regions.

        The visible rendering does not change. Assistive technology, search,
        copy and reflow get real text with real structure. The image(s) the
        text came from should be artifacted in the same plan.
        """
        layers = self.plan.get("text_layers", [])
        if not layers:
            return
        ocr_cache = {}
        total = 0
        for layer in layers:
            pgi = int(layer["page"]) - 1
            page = self.pdf.pages[pgi]
            if layer.get("ocr_lines") is not False and self.workdir:
                f = self.workdir / "ocr" / f"page-{pgi + 1:02}.json"
                if f.exists() and pgi not in ocr_cache:
                    ocr_cache[pgi] = {l["id"]: l for l in json.loads(f.read_text())["lines"]}
            lines_db = ocr_cache.get(pgi, {})
            parent = self.get(layer["parent"])
            if "after" in layer:
                pos = self.index_in_parent(self.get(layer["after"])) + 1
            else:
                pos = layer.get("position", len(self.kids(parent)))
            font_name = ensure_invisible_font(self.pdf, page)
            sp = page.obj.get("/StructParents")
            if sp is None:
                sp = self.d.next_parent_key()
                page.obj.StructParents = sp
                self.pt[sp] = Array([])
                self.d.tree.ParentTreeNextKey = sp + 1
            arr = self.pt.get(int(sp))
            next_mcid = max(len(arr), max_mcid(page) + 1)
            while len(arr) < next_mcid:
                arr.append(pikepdf.Object.parse(b"null"))
            ops = []
            new_elems = []

            def emit(role, block, container):
                nonlocal next_mcid
                text = block["text"] if "text" in block else " ".join(lines_db[i]["text"] for i in block["ocr"])
                olines = sorted((lines_db[i] for i in block.get("ocr", []) if i in lines_db), key=lambda l: (l["bbox"][1], l["bbox"][0]))
                lboxes = [l["bbox"] for l in olines]
                llens = [len(l["text"]) for l in olines]
                bbox = block.get("bbox") or (union_bbox_list(lboxes) if lboxes else None)
                if bbox is None:
                    raise SystemExit(f"text layer block {text[:40]!r} on page {pgi + 1} needs bbox or ocr line ids")
                mcid = next_mcid
                next_mcid += 1
                ops.append(invisible_text_ops(text, bbox, lboxes, float(page.mediabox[3]), font_name, role, mcid, llens))
                e = self.new_elem(role, container)
                e.Pg = page.obj
                e.K = Array([mcid])
                if not text.encode("cp1252", "ignore").decode("cp1252") == text or block.get("actualtext"):
                    e.ActualText = String(block.get("actualtext", text))
                if block.get("lang"):
                    e.Lang = String(block["lang"])
                arr.append(e)
                return e

            for block in layer["blocks"]:
                role = block.get("role", "P")
                if role in ("L", "UL", "OL"):
                    lst = self.new_elem("L", parent)
                    if role == "OL":
                        lst.A = Dictionary(O=Name.List, ListNumbering=Name.Decimal)
                    for item in block["items"]:
                        li = self.new_elem("LI", lst)
                        self.set_kids(lst, self.kids(lst) + [li])
                        if item.get("lbl"):
                            self.set_kids(li, [emit("Lbl", {"text": item["lbl"], "bbox": item.get("lbl_bbox") or item.get("bbox"),
                                                            "ocr": item.get("lbl_ocr", [])}, li)])
                        body = emit("LBody", item, li)
                        self.set_kids(li, self.kids(li) + [body])
                    new_elems.append(lst)
                else:
                    new_elems.append(emit(role, block, parent))
            ks = self.kids(parent)
            ks[pos:pos] = new_elems
            self.set_kids(parent, ks)
            # isolate the original content's graphics state, then draw the invisible text in default space
            page.contents_add(self.pdf.make_stream(b"q\n"), prepend=True)
            page.contents_add(self.pdf.make_stream(b"Q\nq\n" + b"\n".join(ops) + b"\nQ\n"), prepend=False)
            total += sum(1 for _ in layer["blocks"])
        log(f"text layers: {len(layers)} regions, {total} blocks of invisible tagged text")

    # ---- 5a. strip graphics -----------------------------------------
    def apply_strip(self):
        """Artifact an element's own marked content (shape fills, frames) but keep its child elements."""
        targets = [eid for eid, s in self.plan.get("elements", {}).items() if s.get("strip_graphics")]
        per = defaultdict(set)
        holders = {}
        for eid in targets:
            e = self.get(eid)
            pg = self.page_ref(e)
            refs = [r for r in self.d.content_refs(e, self.d.page_index.get(pg.objgen) if pg is not None else None) if r[0] == "mcid"]
            for _, rp, mcid, stm in refs:
                holder = stm if stm is not None else self.pdf.pages[rp].obj
                per[holder.objgen].add(mcid)
                holders[holder.objgen] = holder
            self.retarget_parent_tree(refs, None)
            self.set_kids(e, [k for k in self.kids(e) if is_elem(k) or (isinstance(k, Dictionary) and k.get("/Type") == Name.OBJR)])
        n = sum(rewrite_mcids_as_artifacts(self.pdf, holders[og], m) for og, m in per.items())
        if targets:
            log(f"stripped graphics from {len(targets)} elements ({n} marked-content sequences)")

    # ---- 5b. unwrap --------------------------------------------------
    def apply_unwrap(self):
        targets = [eid for eid, s in self.plan.get("elements", {}).items() if s.get("unwrap")]
        for role in self.plan.get("unwrap_roles", []):
            role = "/" + role.lstrip("/")
            targets += [str(i) for i, e in list(self.by_id.items()) if str(e.S) == role]
        for eid in targets:
            try:
                e = self.get(eid)
            except KeyError:
                continue
            p = self.parent(e)
            if p is None or p.objgen == self.root_elem.objgen:
                log(f"skip unwrap of top-level {eid}")
                continue
            self.explicit_mcrs(e)
            refs = self.d.content_refs(e, self.d.page_index.get(self.page_ref(e).objgen) if self.page_ref(e) is not None else None)
            pos = self.index_in_parent(e)
            kids = self.kids(e)
            for k in kids:
                if is_elem(k):
                    k.P = p
                    if "/Pg" not in k and self.page_ref(e) is not None:
                        k.Pg = self.page_ref(e)
            pks = self.kids(p)
            pks[pos:pos + 1] = kids
            self.set_kids(p, pks)
            if self.page_ref(p) is None and self.page_ref(e) is not None:
                pass
            self.retarget_parent_tree(refs, p)
            self.by_id.pop(e.objgen[0], None)
        log(f"unwrapped {len(targets)} elements")

    # ---- 6. artifacts ------------------------------------------------
    def apply_artifacts(self):
        targets = [eid for eid, s in self.plan.get("elements", {}).items() if s.get("artifact")]
        per_stream = defaultdict(set)  # holder objgen -> mcids
        holders = {}
        kept_annots = 0
        for eid in targets:
            try:
                e = self.get(eid)
            except KeyError:
                continue
            pg = self.page_ref(e)
            pgi = self.d.page_index.get(pg.objgen) if pg is not None else None
            refs = self.d.subtree_refs(e, pgi)
            if any(r[0] == "objr" for r in refs):
                kept_annots += 1
                log(f"WARNING {eid} contains an annotation; it was not artifacted (annotations must stay tagged)")
                continue
            for r in refs:
                _, rp, mcid, stm = r
                holder = stm if stm is not None else self.pdf.pages[rp].obj
                per_stream[holder.objgen].add(mcid)
                holders[holder.objgen] = holder
            self.retarget_parent_tree(refs, None)
            self.detach(e)
            for sub, _, _, _ in self.d.walk(e):
                self.by_id.pop(sub.objgen[0], None)
        n = 0
        for og, mcids in per_stream.items():
            n += rewrite_mcids_as_artifacts(self.pdf, holders[og], mcids)
        log(f"artifacted {len(targets) - kept_annots} elements ({n} marked-content sequences)")

    def prune_empty(self):
        keep = {"/TD", "/TH", "/TR", "/Table", "/Document"}
        changed = True
        removed = 0
        while changed:
            changed = False
            for eid, e in list(self.by_id.items()):
                if self.d.role(e) in keep or self.parent(e) is None:
                    continue
                if not self.kids(e) and "/Alt" not in e and "/ActualText" not in e:
                    self.detach(e)
                    self.by_id.pop(eid)
                    removed += 1
                    changed = True
        log(f"pruned {removed} empty elements")


# ---- content stream rewriting ----------------------------------------

def mcid_of(operands, resources):
    if len(operands) < 2:
        return None
    props = operands[1]
    if isinstance(props, Name) and resources is not None:
        props = resources.get("/Properties", {}).get(props)
    if isinstance(props, Dictionary) and "/MCID" in props:
        return int(props.MCID)
    return None


def rewrite_mcids_as_artifacts(pdf, holder, mcids):
    is_page = holder.get("/Type") == Name.Page
    target = pikepdf.Page(holder) if is_page else holder
    resources = holder.get("/Resources")
    ops = pikepdf.parse_content_stream(target)
    out = []
    count = 0
    for ci in ops:
        operands, op = ci.operands, ci.operator
        if str(op) == "BDC" and mcid_of(operands, resources) in mcids:
            out.append(pikepdf.ContentStreamInstruction([Name.Artifact], pikepdf.Operator("BMC")))
            count += 1
        else:
            out.append(ci)
    data = pikepdf.unparse_content_stream(out)
    if is_page:
        holder.Contents = pdf.make_stream(data)
    else:
        holder.write(data)
    return count


def wrap_untagged_as_artifact(pdf, page):
    """Wrap painting operators that sit outside any marked content in /Artifact BMC…EMC."""
    paint = {"Tj", "TJ", "'", '"', "Do", "f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "sh", "BI"}
    ops = pikepdf.parse_content_stream(page)
    depth = 0
    need = False
    for ci in ops:
        o = str(ci.operator)
        if o in ("BDC", "BMC"):
            depth += 1
        elif o == "EMC":
            depth -= 1
        elif depth == 0 and o in paint:
            need = True
            break
    if not need:
        return False
    out = []
    depth = 0
    open_art = False
    in_text = False
    for ci in ops:
        o = str(ci.operator)
        if o in ("BDC", "BMC"):
            if depth == 0 and open_art:
                out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("EMC")))
                open_art = False
            depth += 1
            out.append(ci)
            continue
        if o == "EMC":
            depth -= 1
            out.append(ci)
            continue
        if o == "BT":
            in_text = True
        if depth == 0 and o in paint and not open_art:
            out.append(pikepdf.ContentStreamInstruction([Name.Artifact], pikepdf.Operator("BMC")))
            open_art = True
        out.append(ci)
        if depth == 0 and open_art and (o == "ET" or (o in paint and not in_text)):
            out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("EMC")))
            open_art = False
        if o == "ET":
            in_text = False
    if open_art:
        out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("EMC")))
    page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(out))
    return True


def union_bbox_list(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def max_mcid(page):
    m = -1
    res = page.obj.get("/Resources", {})
    for ci in pikepdf.parse_content_stream(page):
        if str(ci.operator) == "BDC":
            v = mcid_of(ci.operands, res)
            if v is not None:
                m = max(m, v)
    return m


def ensure_invisible_font(pdf, page):
    """Standard Helvetica for rendering-mode-3 text (PDF/UA-1 7.21.4.1 exempts invisible text from embedding)."""
    res = page.obj.get("/Resources")
    if res is None:
        page.obj.Resources = res = Dictionary()
    fonts = res.get("/Font")
    if fonts is None:
        res.Font = fonts = Dictionary()
    if "/FA11yInv" not in fonts:
        fonts.FA11yInv = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
                                                      Encoding=Name.WinAnsiEncoding))
    return "/FA11yInv"


def _pdf_str(t):
    b = t.encode("cp1252", "replace")
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def invisible_text_ops(text, bbox, line_boxes, page_h, font, role, mcid, line_lens=None):
    """Lay text out over bbox as invisible lines, one per OCR line box when available.

    Words are distributed over the OCR lines in proportion to each OCR line's
    length, so selection highlights land close to the visible words.
    """
    words = text.split()
    n = max(1, len(line_boxes)) if line_boxes else max(1, round((bbox[3] - bbox[1]) / 12))
    n = min(n, max(1, len(words)))
    if not line_lens or len(line_lens) != n:
        line_lens = [1] * n
    total = sum(len(w) + 1 for w in words)
    bounds = []
    acc = 0
    for ln in line_lens[:-1]:
        acc += ln
        bounds.append(total * acc / sum(line_lens))
    lines, cur, pos = [], [], 0
    for w in words:
        if cur and len(lines) < len(bounds) and pos + (len(w) + 1) / 2 > bounds[len(lines)]:
            lines.append(" ".join(cur))
            cur = []
        cur.append(w)
        pos += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    if line_boxes and len(line_boxes) == len(lines):
        boxes = line_boxes
    else:
        h = (bbox[3] - bbox[1]) / len(lines)
        boxes = [[bbox[0], bbox[1] + i * h, bbox[2], bbox[1] + (i + 1) * h] for i in range(len(lines))]
    out = [f"/{role} <</MCID {mcid}>> BDC BT 3 Tr".encode()]
    for line, (x0, t, x1, b) in zip(lines, boxes):
        size = max(1.0, (b - t) * 0.85)
        width = max(1.0, 0.5 * size * len(line))
        tz = max(1.0, min(1000.0, 100 * (x1 - x0) / width))
        out.append(f"/{font[1:]} {size:.2f} Tf {tz:.1f} Tz 1 0 0 1 {x0:.2f} {page_h - b + 0.2 * (b - t):.2f} Tm ".encode()
                   + _pdf_str(line) + b" Tj")
    out.append(b"ET EMC")
    return b"\n".join(out)


# ---- attribute helpers ------------------------------------------------

def get_attr(e, owner, key):
    for a in seq(e.get("/A")):
        if isinstance(a, Dictionary) and a.get("/O") == Name(owner) and key in a:
            return a[key]
    return None


def set_attr(e, owner, key, value):
    attrs = seq(e.get("/A"))
    for a in attrs:
        if isinstance(a, Dictionary) and a.get("/O") == Name(owner):
            a[key] = value
            return
    attrs.append(Dictionary({"/O": Name(owner), key: value}))
    e.A = attrs[0] if len(attrs) == 1 else Array(attrs)


# ---- automatic fixes ---------------------------------------------------

def fix_metadata(pdf, plan):
    meta = plan.get("metadata", {})
    root = pdf.Root
    title = meta.get("title") or str(pdf.docinfo.get("/Title", "")) if pdf.docinfo else meta.get("title")
    if not title or re.fullmatch(r"(?i)(powerpoint presentation|microsoft word.*|untitled.*|document\d*)", title.strip()):
        log("WARNING document title is missing or generic; set metadata.title in the plan")
    lang = meta.get("lang") or str(root.get("/Lang", "")) or "en-US"
    root.Lang = String(lang)
    root.MarkInfo = Dictionary(Marked=True)
    vp = root.get("/ViewerPreferences", Dictionary())
    vp.DisplayDocTitle = True
    root.ViewerPreferences = vp
    info = {"/Title": title, "/Author": meta.get("author"), "/Subject": meta.get("subject"), "/Keywords": meta.get("keywords")}
    for k, v in info.items():
        if v:
            pdf.docinfo[k] = String(v)
    with pdf.open_metadata(set_pikepdf_as_editor=False) as m:
        m.load_from_docinfo(pdf.docinfo, delete_missing=False)
        if title:
            m["dc:title"] = title
        if meta.get("author"):
            m["dc:creator"] = [meta["author"]]
        if meta.get("subject"):
            m["dc:description"] = meta["subject"]
        m["dc:language"] = [lang]
    # pdfuaid has to be written as an extension-free property; pikepdf knows the namespace.
    with pdf.open_metadata(set_pikepdf_as_editor=False) as m:
        m["pdfuaid:part"] = str(plan.get("pdfua_part", 1))
    log(f"metadata: title={title!r} lang={lang} DisplayDocTitle PDF/UA-{plan.get('pdfua_part', 1)} id")


def fix_optional_content(pdf):
    oc = pdf.Root.get("/OCProperties")
    if oc is None:
        return
    configs = [oc.get("/D")] + list(oc.get("/Configs", []))
    for i, c in enumerate(configs):
        if isinstance(c, Dictionary) and "/Name" not in c:
            c.Name = String("Default" if i == 0 else f"Configuration {i}")
            log("optional content configuration named")


def fix_cidset(pdf):
    n = 0
    for obj in pdf.objects:
        if isinstance(obj, Dictionary) and obj.get("/Type") == Name.FontDescriptor and "/CIDSet" in obj:
            del obj["/CIDSet"]
            n += 1
    if n:
        log(f"removed {n} CIDSet streams (optional; incomplete ones violate PDF/UA 7.21.4.2)")


def chars_in_rect(plumber_page, rect, height):
    x0, y0, x1, y1 = rect
    top, bottom = height - y1, height - y0
    cs = [c for c in plumber_page.chars if x0 - 1 <= (c["x0"] + c["x1"]) / 2 <= x1 + 1 and top - 1 <= (c["top"] + c["bottom"]) / 2 <= bottom + 1]
    if not cs:
        return ""
    from pdfplumber.utils import extract_text
    return re.sub(r"\s+", " ", extract_text(cs, x_tolerance=1.5)).strip()


def fix_links(rep: Repair, src_path, plan):
    import pdfplumber
    pdf = rep.pdf
    d = rep.d
    owner = {}
    for e, _, _, pg in d.walk():
        for r in d.content_refs(e, pg):
            if r[0] == "objr":
                owner[r[2].objgen] = e
    overrides = plan.get("link_text", {})
    stats = defaultdict(int)
    with pdfplumber.open(str(src_path)) as pl:
        for i, page in enumerate(pdf.pages):
            h = float(page.mediabox[3])
            for an in page.obj.get("/Annots", []):
                sub = an.get("/Subtype")
                if sub in (Name.Popup,):
                    continue
                rect = [float(v) for v in an.Rect]
                if "/Contents" not in an or not str(an.Contents).strip():
                    txt = overrides.get(str(an.objgen[0])) or (chars_in_rect(pl.pages[i], rect, h) if sub == Name.Link else "")
                    if sub == Name.Link and not txt:
                        act = an.get("/A", {})
                        txt = str(act.get("/URI", "")) or "Link"
                    if txt:
                        an.Contents = String(txt)
                        stats["contents"] += 1
                if sub != Name.Link:
                    continue
                e = owner.get(an.objgen)
                if e is not None and "/Alt" in e and str(e.Alt).strip():
                    an.Contents = String(str(e.Alt))
                if e is not None:
                    if d.role(e) != "/Link":
                        refs = d.content_refs(e)
                        only_this = all(r[0] == "mcid" or r[2].objgen == an.objgen for r in refs)
                        if only_this and d.role(e) in ("/Reference", "/Span", "/P", "/Figure", "/Annot"):
                            if d.role(e) == "/P" or d.role(e) == "/Figure":
                                # wrap the annotation alone in a Link inside this element
                                wrap_objr_in_link(rep, e, an)
                            else:
                                e.S = Name.Link
                            stats["retagged"] += 1
                        else:
                            wrap_objr_in_link(rep, e, an)
                            stats["wrapped"] += 1
                    continue
                # Untagged link: attach to the element owning text under the rectangle.
                host = find_host_for_rect(rep, i, rect, h, pl.pages[i])
                if host is None:
                    log(f"WARNING untagged link on page {i + 1} with no host element; left untagged")
                    continue
                link = rep.new_elem("Link", host)
                link.Pg = page.obj
                key = d.next_parent_key()
                an.StructParent = key
                link.K = Array([Dictionary(Type=Name.OBJR, Obj=an, Pg=page.obj)])
                rep.pt[key] = link
                rep.d.tree.ParentTreeNextKey = key + 1
                rep.set_kids(host, rep.kids(host) + [link])
                stats["created"] += 1
            page.obj.Tabs = Name.S
    log(f"links: {dict(stats)}")


def wrap_objr_in_link(rep, e, an):
    ks = rep.kids(e)
    for idx, k in enumerate(ks):
        if isinstance(k, Dictionary) and k.get("/Type") == Name.OBJR and k.Obj.objgen == an.objgen:
            link = rep.new_elem("Link", e)
            if "/Pg" in k:
                link.Pg = k.Pg
            link.K = Array([k])
            ks[idx] = link
            rep.set_kids(e, ks)
            if "/StructParent" in an:
                rep.pt[int(an.StructParent)] = link
            return link


def find_host_for_rect(rep, pgi, rect, h, plpage):
    x0, y0, x1, y1 = rect
    top, bottom = h - y1, h - y0
    best = None
    for c in plpage.chars:
        if c.get("mcid") is None:
            continue
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        if x0 <= cx <= x1 and top <= cy <= bottom:
            best = c["mcid"]
            break
    if best is None or rep.pt is None:
        return None
    sp = rep.pdf.pages[pgi].obj.get("/StructParents")
    arr = rep.pt.get(int(sp)) if sp is not None else None
    if arr is None or best >= len(arr):
        return None
    host = arr[best]
    return host if isinstance(host, Dictionary) else None


def fix_tables(rep: Repair, plan):
    d = rep.d
    stats = defaultdict(int)
    for e, _, _, pg in list(d.walk()):
        if d.role(e) != "/Table":
            continue
        rows = []

        def collect(x):
            for k in rep.kids(x):
                if not is_elem(k):
                    continue
                r = d.role(k)
                if r == "/TR":
                    rows.append(k)
                elif r in ("/THead", "/TBody", "/TFoot"):
                    collect(k)
        collect(e)
        if not rows:
            continue
        spec = plan.get("tables", {}).get(str(e.objgen[0]), {})
        # occupancy grid with row/col spans
        occupied = defaultdict(set)
        widths = []
        cells_by_row = []
        for ri, row in enumerate(rows):
            col = 0
            cells = [k for k in rep.kids(row) if is_elem(k) and d.role(k) in ("/TH", "/TD")]
            cells_by_row.append(cells)
            for c in cells:
                while col in occupied[ri]:
                    col += 1
                cs = int(get_attr(c, "/Table", "/ColSpan") or 1)
                rs = int(get_attr(c, "/Table", "/RowSpan") or 1)
                for dr in range(rs):
                    for dc in range(cs):
                        occupied[ri + dr].add(col + dc)
                col += cs
            widths.append(max(occupied[ri]) + 1 if occupied[ri] else 0)
        ncols = max(widths)
        for ri, row in enumerate(rows):
            missing = ncols - len(occupied[ri])
            if missing > 0 and spec.get("pad", True):
                for _ in range(missing):
                    td = rep.new_elem("TD", row)
                    rep.set_kids(row, rep.kids(row) + [td])
                stats["padded_cells"] += missing
        for ri, ci, ids in spec.get("place", []):
            # re-read cells (padding may have added some), then move content into the cell
            cells = [k for k in rep.kids(rows[ri]) if is_elem(k) and d.role(k) in ("/TH", "/TD")]
            for x in ids:
                rep.move_into(rep.get(x), cells[ci])
            stats["placed"] += len(ids)
        cells_by_row = [[k for k in rep.kids(r) if is_elem(k) and d.role(k) in ("/TH", "/TD")] for r in rows]
        hr = spec.get("header_rows")
        hc = spec.get("header_cols")
        for ri, cells in enumerate(cells_by_row):
            for ci, c in enumerate(cells):
                want_th = (hr is not None and ri < hr) or (hc is not None and ci < hc)
                if want_th and d.role(c) == "/TD":
                    c.S = Name.TH
                    stats["to_th"] += 1
                if d.role(c) == "/TH" and get_attr(c, "/Table", "/Scope") is None:
                    scope = "/Column" if (ri == 0 or (hr and ri < hr)) else ("/Row" if ci == 0 or (hc and ci < hc) else "/Both")
                    set_attr(c, "/Table", "/Scope", Name(scope))
                    stats["scoped"] += 1
        if "summary" in spec:
            set_attr(e, "/Table", "/Summary", String(spec["summary"]))
    log(f"tables: {dict(stats)}")


def fix_lists(rep: Repair):
    d = rep.d
    n = 0
    for e, _, _, _ in list(d.walk()):
        if d.role(e) != "/LI":
            continue
        ks = rep.kids(e)
        if all(is_elem(k) and d.role(k) in ("/Lbl", "/LBody") for k in ks):
            continue
        rep.explicit_mcrs(e)
        ks = rep.kids(e)
        lbls = [k for k in ks if is_elem(k) and d.role(k) == "/Lbl"]
        rest = [k for k in ks if not (is_elem(k) and d.role(k) == "/Lbl")]
        bodies = [k for k in rest if is_elem(k) and d.role(k) == "/LBody"]
        if len(bodies) == 1 and len(rest) == 1:
            continue
        body = rep.new_elem("LBody", e)
        refs = [("mcid", None, None, None)]
        for k in rest:
            if is_elem(k):
                k.P = body
        rep.set_kids(body, rest)
        rep.set_kids(e, lbls + [body])
        # MCRs moved into body: retarget parent tree
        pg = rep.page_ref(e)
        refs = d.content_refs(body, d.page_index.get(pg.objgen) if pg is not None else None)
        rep.retarget_parent_tree(refs, body)
        n += 1
    if n:
        log(f"lists: wrapped {n} list item bodies in LBody")


def fix_list_numbering(rep: Repair):
    """Lists with labels carry ListNumbering (PDF/UA-2 8.2.5.25; harmless for UA-1)."""
    d = rep.d
    for e, _, _, _ in list(d.walk()):
        if d.role(e) != "/L" or get_attr(e, "/List", "/ListNumbering") is not None:
            continue
        lbls = [k for li in rep.kids(e) if is_elem(li) for k in rep.kids(li) if is_elem(k) and d.role(k) == "/Lbl"]
        if lbls:
            set_attr(e, "/List", "/ListNumbering", Name("/Disc"))


def fix_untagged(pdf):
    n = sum(1 for p in pdf.pages if wrap_untagged_as_artifact(pdf, p))
    if n:
        log(f"wrapped untagged painting operators as artifacts on {n} pages")


def heading_report(rep: Repair):
    levels = []
    for e, _, _, _ in rep.d.walk():
        m = re.match(r"^/H([1-6])$", rep.d.role(e))
        if m:
            levels.append(int(m.group(1)))
    issues = []
    prev = 0
    for lv in levels:
        if lv > prev + 1:
            issues.append(f"H{prev}→H{lv}")
        prev = lv
    log(f"headings: {len(levels)} ({levels.count(1)} H1); skipped levels: {issues or 'none'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("plan")
    ap.add_argument("output")
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    ap.add_argument("--trace-ids", action="store_true",
                    help="stamp /ID=src-<objnum> on every element so audit.py of the output shows source ids (preview only)")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    auto = {"metadata": True, "optional_content": True, "cidset": True, "links": True, "tables": True,
            "lists": True, "untagged": True, "prune": True, **plan.get("auto", {})}
    d = Doc(a.input)
    if d.tree is None:
        raise SystemExit("Input is untagged. Use the rebuild path (build_html.py → render_pdf.cjs → finalize.py) "
                         "or tag it first; repair.py edits an existing structure tree.")
    rep = Repair(d, plan, Path(a.workdir) if a.workdir else None)
    if a.trace_ids:
        for i, e in rep.by_id.items():
            e.ID = String(f"src-{i}")
    rep.apply_merge()
    rep.apply_new()
    rep.apply_order()
    rep.expand_groups()
    rep.apply_text_layers()
    rep.apply_elements()
    rep.apply_strip()
    rep.apply_unwrap()
    rep.apply_artifacts()
    if auto["metadata"]:
        fix_metadata(d.pdf, plan)
    if auto["optional_content"]:
        fix_optional_content(d.pdf)
    if auto["cidset"]:
        fix_cidset(d.pdf)
    if auto["links"]:
        fix_links(rep, a.input, plan)
    if auto["tables"]:
        fix_tables(rep, plan)
    if auto["lists"]:
        fix_lists(rep)
    if auto["lists"]:
        fix_list_numbering(rep)
    if auto["prune"]:
        rep.prune_empty()
    if auto["untagged"]:
        fix_untagged(d.pdf)
    d.tree.ParentTreeNextKey = d.next_parent_key()
    heading_report(rep)
    d.save(a.output)
    # sanity: reopen and walk
    chk = Doc(a.output)
    n = sum(1 for _ in chk.walk())
    log(f"saved {a.output}: {n} structure elements")
    print("\n".join(LOG))
    if a.report:
        write_json(a.report, {"log": LOG})


if __name__ == "__main__":
    main()
