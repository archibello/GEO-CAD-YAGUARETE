#!/usr/bin/env bash
# Arma el PDF del manual a partir de las páginas .md de esta carpeta.
# Uso: bash manual/armar_pdf.sh [salida.pdf]
# Necesita pandoc y Google Chrome (o Chromium).
set -euo pipefail
cd "$(dirname "$0")"
salida="${1:-Manual_GEO-CAD-YAGUARETE.pdf}"
case "$salida" in /*) ;; *) salida="$OLDPWD/$salida" ;; esac

chrome="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
html="$(mktemp --suffix=.html -p .)"
trap 'rm -f "$html"' EXIT

# Las páginas en orden: 01_..., 02_..., (y luego el final).
paginas=( $(ls [0-9][0-9]_*.md | sort) )

pandoc "${paginas[@]}" --standalone --metadata title="Manual de usuario de GEO-CAD-YAGUARETÉ" \
  --metadata subtitle="Un abrazo entre tres fronteras: QGIS, IngeCAD y Google Earth" --metadata lang=es --css estilo_pdf.css --embed-resources -o "$html"

"$chrome" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$salida" "file://$PWD/$(basename "$html")" 2>/dev/null
echo "PDF: $salida"
