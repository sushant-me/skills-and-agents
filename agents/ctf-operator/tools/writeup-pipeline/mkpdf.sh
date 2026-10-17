#!/bin/bash
# md -> styled HTML -> PDF, using the existing md2html.py renderer and the
# CDP browser at 127.0.0.1:9222 (printBackground=true is required for the theme).
# usage: ./mkpdf.sh <input.md> <output.pdf>
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
MD="$1"; PDF="$2"
HTML="${PDF%.pdf}.html"
python3 "$DIR/md2html.py" "$MD" "$HTML"
node "$DIR/print.mjs" "$HTML" "$PDF"
ls -l "$PDF"
pdfinfo "$PDF" | grep -E '^(Pages|Page size|File size)'
