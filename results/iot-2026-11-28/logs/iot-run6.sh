#!/bin/bash
# Campaign 2026-11-28-t054, after run5: the translated configurations with rml2sparql-generate
# 0.5.4 (tag v0.5.4, d81cdee; kgc-bench main de4d6d9 or later), SPARQL-Generate 2.6.3 and
# pysparql-generate 0.4.2 unchanged: GTFS 1-1000, gtfs-inverted 1 and 10, gtfs-feeds K = 10,
# 100, 1000 (Maxime, 2026-11-28: the translated runs wait for the optimised translator).
set -u
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
ID=2026-11-28-t054
plog() { echo "$(date -Iseconds) campaign=$ID event=$*" >> $KGC_BENCH_PUBLIC_LOG; }
git fetch -q origin && git checkout -q origin/main -- harness scripts versions.env workloads conformance tests README.md REPRODUCE.md \
  || { plog "checkout-failed"; exit 1; }
./scripts/fetch_testcases.sh > $HOME/run6-fetch.log 2>&1 || { plog "fetch-failed"; exit 1; }
grep -q KGC_BENCH_TRANSLATION_TIMEOUT harness/engines.py || { plog "harness-too-old"; exit 1; }
git -C third_party/rml-to-sparql-generate rev-parse HEAD | grep -q '^d81cdee' || { plog "translator-wrong-commit"; exit 1; }
[ -s engines/sparql-generate-2.6.3.jar ] || { plog "sg-2.6.3-jar-missing"; exit 1; }
[ "$(cat engines/pysparql-generate/COMMIT)" = "$(sed -n 's/^PYSPARQL_GENERATE_COMMIT=//p' versions.env)" ] || { plog "pysg-wrong-export"; exit 1; }
# gtfs-feeds code: branch iot-feeds merged with main (staged in kgc-bench-feeds-next by the agent)
F=$HOME/kgc-bench-feeds
if [ -d $HOME/kgc-bench-feeds-next ]; then mv $F $HOME/kgc-bench-feeds-v3 && mv $HOME/kgc-bench-feeds-next $F; fi
grep -q KGC_BENCH_TRANSLATION_TIMEOUT $F/harness/engines.py || { plog "feeds-code-too-old"; exit 1; }
V=$(grep -E '^(SPARQL_GENERATE_VERSION|RML2SG_COMMIT|PYSPARQL_GENERATE_COMMIT)=' versions.env | tr '\n' ' ')
plog "start versions=$V feeds=$(cat $F/COMMIT)"
T="sg-java-translated pysparql-generate-translated"
python -m harness.perf --workloads gtfs --scales 1 10 100 1000 --runs 5 --timeout-at 1000=3600 \
  --engines $T --campaign $ID > $HOME/run6-gtfs.log 2>&1
plog "gtfs end exit=$?"
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines $T --campaign $ID > $HOME/run6-inv.log 2>&1
plog "gtfs-inverted end exit=$?"
( cd $F && KGC_BENCH_TRANSLATION_TIMEOUT=3600 KGC_BENCH_RESULTS=$B/results/feeds-$ID \
    KGC_BENCH_REFERENCE_RESULTS=$B/results/feeds-2026-11-28-v3 \
    python -m harness.perf --workloads gtfs-feeds --scales 10 100 1000 --runs 5 --timeout-at 1000=3600 \
    --engines $T --campaign $ID > $HOME/run6-feeds.log 2>&1 )
plog "gtfs-feeds end exit=$?"
plog all-done
