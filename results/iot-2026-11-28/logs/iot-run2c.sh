#!/bin/bash
# After kgc-bench-run2b: (1) gtfs-inverted again with the mapping in the style of the original
# (kgc-bench 3fca38b), the engines that read the RML mapping, campaign 2026-11-27-inv;
# (2) ours at GTFS 1000 (campaign.sh had skipped its perf-gtfs step as done).
set -u
while systemctl is-active --quiet kgc-bench-run2 || systemctl is-active --quiet kgc-bench-run2b; do sleep 60; done
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
plog() { echo "$(date -Iseconds) campaign=$1 event=$2" >> $KGC_BENCH_PUBLIC_LOG; }
git fetch -q origin && git checkout -q origin/main -- workloads/gtfs-inverted scripts/gtfs_mappings.py
grep -q "a rr:SubjectMap" workloads/gtfs-inverted/gtfs-inverted-csv.rml.ttl || { plog inv mapping-not-updated; exit 1; }
[ "$(cat engines/pysparql-generate/COMMIT)" = c8782c0291 ] || { plog inv pysg-wrong-export; exit 1; }
FLEX="KGC_BENCH_PIN_FLEXRML_VERSION=3.1.0+patched KGC_BENCH_PATCHES=no-natural-datatype-for-csv-xml,fno-parameter-iri"
SDM="KGC_BENCH_PYTHONPATH_SDM_RDFIZER=$B/engines/sdm-rdfizer-patched KGC_BENCH_PATCHES=base-iri,join-term-maps,postgres-port,natural-datatypes,language-map-reference,reference-iri"
ROCK="KGC_BENCH_PIN_ROCKETRML_VERSION=3.0.0+patched KGC_BENCH_PATCHES=join-empty-values,join-duplicates,double-lexical-form,stream-nquads,graph-maps,multiple-classes"
ID=2026-11-27-inv
plog $ID "start mapping=$(git rev-parse --short origin/main)"
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines sg-java sg-java-translated pysparql-generate-translated morph-kgc morph-kgc-4p rmlmapper rpt burp rmlstreamer \
  --campaign $ID > $HOME/inv-main.log 2>&1
for e in flexrml sdm-rdfizer rocketrml; do
  case $e in flexrml) envs=$FLEX;; sdm-rdfizer) envs=$SDM;; rocketrml) envs=$ROCK;; esac
  env $envs KGC_BENCH_RESULTS=$B/results/patched/$e/iot-$ID KGC_BENCH_REFERENCE_RESULTS=$B/results \
    python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 --engines $e --campaign $ID >> $HOME/inv-patched.log 2>&1
done
plog $ID end
ID=2026-11-27-v2
plog $ID "gtfs-1000 start"
python -m harness.perf --workloads gtfs --scales 1000 --runs 5 --timeout-at 1000=3600 \
  --engines sg-java sg-java-translated pysparql-generate pysparql-generate-translated --campaign $ID > $HOME/v2-1000.log 2>&1
plog $ID "gtfs-1000 end exit=$?"
plog $ID all-done
