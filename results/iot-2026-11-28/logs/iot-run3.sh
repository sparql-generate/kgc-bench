#!/bin/bash
# Replaces run2c and run2d (Maxime, 2026-11-27 18:50). After kgc-bench-run2 and -run2b:
# (1) gtfs-inverted again, mapping in the style of the original (kgc-bench 3fca38b), engines
#     that read the RML mapping except the translated ones, campaign 2026-11-27-inv;
# (2) hand-written ours at GTFS 1000 (campaign 2026-11-27-v2);
# (3) RMLMapper with five patches (#288), GTFS 1-1000 and gtfs-inverted 1, 10;
# (4) translator 0.5.1 (R8 both ways), once pinned on origin/main: translated ours,
#     GTFS 1-1000 and gtfs-inverted 1, 10, campaign 2026-11-27-v3.
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
RMLM="KGC_BENCH_PIN_RMLMAPPER_VERSION=development-86e961d7+patched5 KGC_BENCH_PATCHES=natural-datatypes-json,json-bracket-references,target-compression,join-term-maps,self-join-child-subject"
patched() {  # patched <engine> <envs> <campaign> <workload> <extra args...>
  local e=$1 envs=$2 id=$3 w=$4; shift 4
  env $envs KGC_BENCH_RESULTS=$B/results/patched/$e/iot-$id KGC_BENCH_REFERENCE_RESULTS=$B/results \
    python -m harness.perf --workloads $w --runs 5 --engines $e --campaign $id "$@" >> $HOME/run3-patched-$e.log 2>&1
  plog $id "patched end engine=$e workload=$w exit=$?"
}
# (1)
ID=2026-11-27-inv; plog $ID "start mapping=$(git rev-parse --short origin/main)"
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines sg-java morph-kgc morph-kgc-4p rmlmapper rpt burp rmlstreamer --campaign $ID > $HOME/run3-inv.log 2>&1
patched flexrml "$FLEX" $ID gtfs-inverted --scales 1 10
patched sdm-rdfizer "$SDM" $ID gtfs-inverted --scales 1 10
patched rocketrml "$ROCK" $ID gtfs-inverted --scales 1 10
patched rmlmapper "$RMLM" $ID gtfs-inverted --scales 1 10
# (2)
ID=2026-11-27-v2; plog $ID "gtfs-1000 hand-written start"
python -m harness.perf --workloads gtfs --scales 1000 --runs 5 --timeout-at 1000=3600 \
  --engines sg-java pysparql-generate --campaign $ID > $HOME/run3-1000.log 2>&1
# (3)
patched rmlmapper "$RMLM" $ID gtfs --scales 1 10 100 1000 --timeout-at 1000=3600
# (4)
OLD=0d3c33e8db46e115f18a1a0bfdf2f1cac1c363db
for i in $(seq 72); do
  git fetch -q origin
  NEW=$(git show origin/main:versions.env | sed -n 's/^RML2SG_COMMIT=//p')
  [ -n "$NEW" ] && [ "$NEW" != "$OLD" ] && break
  sleep 300
done
[ "$NEW" != "$OLD" ] || { plog 2026-11-27-v3 "translator-0.5.1-not-pinned"; exit 1; }
git checkout -q origin/main -- versions.env && ./scripts/fetch_testcases.sh > /dev/null
ID=2026-11-27-v3; plog $ID "start translator=$NEW"
python -m harness.perf --workloads gtfs --scales 1 10 100 1000 --runs 5 --timeout-at 1000=3600 \
  --engines sg-java-translated pysparql-generate-translated --campaign $ID > $HOME/run3-v3-gtfs.log 2>&1
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines sg-java-translated pysparql-generate-translated --campaign $ID > $HOME/run3-v3-inv.log 2>&1
plog $ID all-done
