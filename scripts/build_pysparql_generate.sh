#!/bin/sh
# Exports a commit of the sibling working copy ../pysparql-generate (default
# the release pinned in versions.env, PYSPARQL_GENERATE_COMMIT; PYSG_COMMIT=<sha> for another) into build/, WITHOUT touching it, and
# points engines/pysparql-generate at it. The harness runs that export (its
# src/ first on PYTHONPATH): it measures a commit, never a working copy that
# may be under edit. Its dependencies are those of the interpreter that runs it
# (KGC_BENCH_PYSG_PYTHON: the Python of a venv of its own, with pysparql-generate installed
# for its dependencies; never the harness's venv, REPRODUCE.md).
#
#   scripts/build_pysparql_generate.sh   -> engines/pysparql-generate -> build/pysparql-generate-<sha>
set -e
cd "$(dirname "$0")/.."
. ./versions.env
SRC=${PYSPARQL_GENERATE_SRC:-../pysparql-generate}
if [ ! -d "$SRC/.git" ]; then
    # no sibling working copy (an installation from scratch): the public repository
    SRC=third_party/pysparql-generate
    [ -d "$SRC/.git" ] || git clone --quiet "$PYSPARQL_GENERATE_REPO" "$SRC"
    git -C "$SRC" fetch --quiet --tags origin
fi
SHA=$(git -C "$SRC" rev-parse --short=10 "${PYSG_COMMIT:-${PYSPARQL_GENERATE_COMMIT:-HEAD}}")
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
