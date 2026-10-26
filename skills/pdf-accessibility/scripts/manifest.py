#!/usr/bin/env python3
"""Hand-off step: SHA-256 manifest of the delivered files, so evidence is tied to exact bytes.

Usage: manifest.py OUT_DIR [--out OUT_DIR/MANIFEST-SHA256.json] [--check]

Hashes every file under OUT_DIR (except the manifest itself) and records size and, for
PDFs, the page count. Run it last, after the final validation; any later change to a
deliverable makes the report's numbers stale, and --check shows which files changed.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pymupdf as fitz


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true", help="compare with an existing manifest instead of writing")
    a = ap.parse_args()
    root = Path(a.dir)
    out = Path(a.out) if a.out else root / "MANIFEST-SHA256.json"
    files = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.resolve() == out.resolve() or p.name == ".DS_Store":
            continue
        rec = {"sha256": sha256(p), "bytes": p.stat().st_size}
        if p.suffix.lower() == ".pdf":
            with fitz.open(p) as d:
                rec["pages"] = d.page_count
        files[p.relative_to(root).as_posix()] = rec
    if a.check:
        old = json.loads(out.read_text())["files"]
        changed = sorted(k for k in set(old) | set(files) if old.get(k, {}).get("sha256") != files.get(k, {}).get("sha256"))
        for k in changed:
            print(("changed: " if k in old and k in files else "added: " if k in files else "missing: ") + k)
        sys.exit(1 if changed else 0)
    out.write_text(json.dumps({"files": files}, indent=1))
    print(f"wrote {out}: {len(files)} files")


if __name__ == "__main__":
    main()
