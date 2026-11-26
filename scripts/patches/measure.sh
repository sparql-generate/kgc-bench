#!/bin/sh
# Measure one RML engine on the seven suites, its rows in a results directory of
# its own: scripts/patches/measure.sh <engine> <variant> [harness options...]
#   results/patched/<engine>/<variant>/conformance.csv
# The engine is the one the environment points at (KGC_BENCH_PIN_<KEY>,
# KGC_BENCH_PYTHONPATH_<ENGINE>, KGC_BENCH_PATCHES: scripts/patches/env.sh).
set -e
engine=$1; variant=$2; shift 2
cd "$(dirname "$0")/../.."
out=results/patched/$engine/$variant
mkdir -p "$out"
work=${KGC_BENCH_CONFORMANCE_WORK:-${TMPDIR:-/tmp}/kgc-bench-patched/$engine/$variant}
mkdir -p "$work"
KGC_BENCH_RESULTS=$out KGC_BENCH_CONFORMANCE_WORK=$work \
  python -m harness.conformance --modes rml --engines "$engine" --quiet "$@"
