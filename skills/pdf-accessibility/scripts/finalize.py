#!/usr/bin/env python3
"""Rebuild path, step 3: turn Chromium's tagged PDF into a PDF/UA-1 file.

Usage: finalize.py CHROME.pdf OUT.pdf --title "Document title" [--lang en-US] [--author ...] [--subject ...]

Runs repair.py's automatic fixes on the Chromium output (no judgement plan is
needed because the HTML already carried the semantics):
  * PDF 2.0-only roles that PDF/UA-1 readers may not know (Strong, Em) → Span
  * LI children normalised to Lbl/LBody; link annotations tagged with Contents
  * running header/footer and other untagged painting marked as Artifact
  * Lang, title, DisplayDocTitle, XMP dc:title and pdfuaid:part, Tabs /S
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--title", required=True)
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--author")
    ap.add_argument("--subject")
    a = ap.parse_args()
    plan = {"metadata": {k: v for k, v in {"title": a.title, "lang": a.lang, "author": a.author, "subject": a.subject}.items() if v},
            "retag_roles": {"Strong": "Span", "Em": "Span"}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(plan, f)
    res = subprocess.run([sys.executable, str(Path(__file__).with_name("repair.py")), a.input, f.name, a.output])
    Path(f.name).unlink()
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
