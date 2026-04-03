#!/bin/bash
set -euo pipefail

TRIPLE=$(rustc -vV | grep 'host:' | cut -d' ' -f2)
OUT_DIR="desktop/src-tauri/binaries"
BINARY="ace-server-${TRIPLE}"
mkdir -p "$OUT_DIR"

echo "Compiling ACE for ${TRIPLE}..."

PYTHONPATH=src uv run python -m nuitka \
    --onefile \
    --onefile-tempdir-spec="{CACHE_DIR}/ace-coder" \
    --output-dir=/tmp/ace-build \
    --output-filename="${BINARY}" \
    --include-package=ace \
    --include-data-dir=src/ace/static=ace/static \
    --include-data-dir=src/ace/templates=ace/templates \
    src/ace/__main__.py

# Nuitka --onefile may ignore --output-dir in some versions; check both locations
if [ -f "/tmp/ace-build/${BINARY}" ]; then
    cp "/tmp/ace-build/${BINARY}" "$OUT_DIR/"
elif [ -f "${BINARY}" ]; then
    cp "${BINARY}" "$OUT_DIR/"
else
    echo "ERROR: compiled binary '${BINARY}' not found" >&2
    exit 1
fi

echo "Binary placed at ${OUT_DIR}/${BINARY}"
