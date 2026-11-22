#!/bin/sh
# Runs any command (a build, an ad hoc engine run) under the memory cap of the
# harness: a transient systemd scope in agents-kgcbench.slice, OOM score 1000
# (harness/sandbox.py).
#
#   KGC_BENCH_MEM_CAP=24G scripts/capped.sh java -jar engines/rpt-2.0.0-rc7.jar ...
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m harness.sandbox -- "$@"
