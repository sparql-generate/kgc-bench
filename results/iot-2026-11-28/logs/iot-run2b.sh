#!/bin/bash
# After kgc-bench-run2: pysparql-generate 0.4.0 (c8782c0291) again on GTFS 1-100 and
# gtfs-inverted 1, 10, the rows of campaign 2026-11-27-v2 measured with the stale export
# 4e912d0aaa (0.3.0) removed first (the sibling clone had not been fetched).
set -u
while systemctl is-active --quiet kgc-bench-run2; do sleep 60; done
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
ID=2026-11-27-v2
plog() { echo "$(date -Iseconds) campaign=$ID event=$*" >> $KGC_BENCH_PUBLIC_LOG; }
git pull -q --ff-only || true
./scripts/build_pysparql_generate.sh > /dev/null || { plog "pysg-build-failed"; exit 1; }
[ "$(cat engines/pysparql-generate/COMMIT)" = c8782c0291 ] || { plog "pysg-wrong-export"; exit 1; }
python3 - <<'PY'
import csv
f = "results/perf.csv"
rows = list(csv.DictReader(open(f, newline="")))
keep = [r for r in rows if not (r.get("campaign") == "2026-11-27-v2" and "4e912d0aaa" in r.get("version", ""))]
w = csv.DictWriter(open(f, "w", newline=""), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(keep)
print(len(rows) - len(keep), "stale rows removed")
PY
plog "pysg-rerun start"
python -m harness.perf --workloads gtfs --scales 1 10 100 --runs 5 \
  --engines sg-java pysparql-generate pysparql-generate-translated --campaign $ID > $HOME/v2b-gtfs.log 2>&1
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines sg-java pysparql-generate pysparql-generate-translated --campaign $ID > $HOME/v2b-inverted.log 2>&1
plog "pysg-rerun end"
