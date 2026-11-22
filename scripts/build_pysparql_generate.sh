#!/bin/sh
# Exports a commit of the sibling working copy ../pysparql-generate (default
# HEAD; PYSG_COMMIT=<sha> for another) into build/, WITHOUT touching it, and
# points engines/pysparql-generate at it. The harness runs that export (its
# src/ first on PYTHONPATH): it measures a commit, never a working copy that
# may be under edit. The dependencies are those of the active environment
# (pip install -e ../pysparql-generate once, for them).
#
#   scripts/build_pysparql_generate.sh   -> engines/pysparql-generate -> build/pysparql-generate-<sha>
set -e
cd "$(dirname "$0")/.."
SRC=${PYSPARQL_GENERATE_SRC:-../pysparql-generate}
SHA=$(git -C "$SRC" rev-parse --short=10 "${PYSG_COMMIT:-HEAD}")
OUT="build/pysparql-generate-$SHA"
if [ ! -d "$OUT/src/sparql_generate" ]; then
    rm -rf "$OUT"
    mkdir -p "$OUT"
    git -C "$SRC" archive "$SHA" src pyproject.toml | tar -x -C "$OUT"
    echo "$SHA" > "$OUT/COMMIT"
fi
mkdir -p engines
ln -sfn "../$OUT" engines/pysparql-generate
echo "engines/pysparql-generate -> $OUT"
