#!/usr/bin/env bash
# Install the local toolchain for the pdf-accessibility skill. Everything runs offline after this.
#   Python: pikepdf, pymupdf, pdfplumber, pypdf, Pillow
#   System: tesseract (OCR), qpdf, poppler-utils, Java 11+ (for veraPDF)
#   veraPDF: PDF/UA-1 / PDF/UA-2 validator, fetched from Maven Central into ~/.cache/pdf-a11y/verapdf
#   Node: playwright (Chromium) and axe-core for the rebuild path
# Safe to re-run. Use --check to only report what is missing.
set -euo pipefail
CACHE="${PDF_A11Y_CACHE:-$HOME/.cache/pdf-a11y}"
VERA_VERSION="${VERA_VERSION:-1.28.2}"
CHECK=0; [[ "${1:-}" == "--check" ]] && CHECK=1
mkdir -p "$CACHE"
have() { command -v "$1" >/dev/null 2>&1; }
missing=()

py_ok() { python3 -c "import pikepdf, pymupdf, pdfplumber, PIL" 2>/dev/null; }
if ! py_ok; then
  missing+=(python-packages)
  if [[ $CHECK == 0 ]]; then
    python3 -m pip install --quiet pikepdf pymupdf pdfplumber pypdf Pillow 2>/dev/null \
      || python3 -m pip install --quiet --break-system-packages pikepdf pymupdf pdfplumber pypdf Pillow
  fi
fi

pkgs=()
have tesseract || pkgs+=(tesseract)
have qpdf || pkgs+=(qpdf)
have pdftoppm || pkgs+=(poppler)
have java || pkgs+=(java)
if ((${#pkgs[@]})); then
  missing+=("${pkgs[@]}")
  if [[ $CHECK == 0 ]]; then
    if have brew; then
      brew install tesseract qpdf poppler openjdk || true
    elif have apt-get; then
      SUDO=""; [[ $(id -u) != 0 ]] && SUDO="sudo"
      $SUDO apt-get install -y -q tesseract-ocr tesseract-ocr-eng qpdf poppler-utils default-jre-headless \
        || { $SUDO apt-get update -q && $SUDO apt-get install -y -q tesseract-ocr tesseract-ocr-eng qpdf poppler-utils default-jre-headless; }
    else
      echo "Install manually: ${pkgs[*]}" >&2
    fi
  fi
fi

# veraPDF CLI from Maven Central (works where the veraPDF download site is blocked).
VERA_DIR="$CACHE/verapdf"
if [[ ! -x "$VERA_DIR/verapdf" ]] && ! have verapdf; then
  missing+=(verapdf)
  if [[ $CHECK == 0 ]]; then
    mkdir -p "$VERA_DIR/lib"
    if have mvn; then
      cat > "$VERA_DIR/pom.xml" <<EOF
<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<groupId>local</groupId><artifactId>verapdf-cli</artifactId><version>1</version>
<dependencies><dependency><groupId>org.verapdf.apps</groupId><artifactId>greenfield-apps</artifactId><version>$VERA_VERSION</version></dependency></dependencies></project>
EOF
      (cd "$VERA_DIR" && mvn -q dependency:copy-dependencies -DoutputDirectory=lib \
        && mvn -q dependency:copy -Dartifact=org.verapdf.apps:greenfield-apps:$VERA_VERSION -DoutputDirectory=lib)
    else
      echo "Maven not found. Install veraPDF from https://verapdf.org/software/ and put 'verapdf' on PATH," >&2
      echo "or install Maven and re-run this script." >&2
    fi
    if ls "$VERA_DIR"/lib/*.jar >/dev/null 2>&1; then
      cat > "$VERA_DIR/verapdf" <<EOF
#!/bin/sh
exec java -Xmx2g -cp "$VERA_DIR/lib/*" org.verapdf.apps.GreenfieldCliWrapper "\$@"
EOF
      chmod +x "$VERA_DIR/verapdf"
    fi
  fi
fi

# Node side: playwright + axe-core (rebuild path only).
if have node; then
  if ! node -e "require('playwright')" 2>/dev/null && [[ ! -d "$CACHE/node_modules/playwright" ]]; then
    missing+=(playwright)
    [[ $CHECK == 0 ]] && (cd "$CACHE" && npm install --silent --no-audit --no-fund playwright && npx playwright install chromium)
  fi
  if [[ ! -f "$CACHE/node_modules/axe-core/axe.min.js" ]]; then
    missing+=(axe-core)
    [[ $CHECK == 0 ]] && (cd "$CACHE" && npm install --silent --no-audit --no-fund axe-core@4.10.3)
  fi
else
  missing+=(node)
fi

if [[ $CHECK == 1 ]]; then
  if ((${#missing[@]})); then echo "missing: ${missing[*]}"; exit 1; else echo "all tools present"; fi
else
  echo "pdf-accessibility toolchain ready in $CACHE"
  [[ -x "$VERA_DIR/verapdf" ]] && echo "veraPDF: $VERA_DIR/verapdf (scripts find it automatically)"
  [[ -d "$CACHE/node_modules/playwright" ]] && echo "Playwright: export PLAYWRIGHT_MODULE=$CACHE/node_modules/playwright"
fi
