#!/bin/bash
# On iot, as kgcbench: campaign 2026-11-27-v2 (Maxime, 2026-11-27): SPARQL-Generate 2.6.2,
# rml-to-sparql-generate 0.5.0, pysparql-generate 0.4.0 (kgc-bench c715bd4 and later), and
# FlexRML, SDM-RDFizer, RocketRML with the proposed patches; GTFS 1-1000, gtfs-inverted 1, 10.
set -u
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
plog() { echo "$(date -Iseconds) campaign=$ID event=$*" >> $KGC_BENCH_PUBLIC_LOG; }
ID=2026-11-27-v2
git pull -q --ff-only || { plog "git-pull-failed"; exit 1; }
grep -q "^SPARQL_GENERATE_VERSION=2.6.2" versions.env || { plog "wrong-pins"; exit 1; }
SKIP_PIP=1 ./scripts/fetch_engines.sh > /dev/null
$KGC_BENCH_PYSG_PYTHON -m pip install -q "pysparql-generate[sql]==0.4.0" > /dev/null 2>&1
$KGC_BENCH_PYSG_PYTHON -m pip uninstall -q -y pysparql-generate > /dev/null 2>&1   # deps only: the pinned export runs
./scripts/build_pysparql_generate.sh > /dev/null
plog "start versions=$(grep -E '^(SPARQL_GENERATE_VERSION|RML2SG_COMMIT|PYSG_COMMIT)=' versions.env | tr '\n' ' ')"
OURS="sg-java sg-java-translated pysparql-generate pysparql-generate-translated"
REST="morph-kgc morph-kgc-4p rmlmapper sdm-rdfizer rpt sparql-anything rocketrml flexrml burp rmlstreamer shexml"
export QUIET_LOAD=1.5 QUIET_WAIT=3600 RUNS=5 LIMIT_TIME_S_AT="1000=3600"
FLEX="KGC_BENCH_PIN_FLEXRML_VERSION=3.1.0+patched KGC_BENCH_PATCHES=no-natural-datatype-for-csv-xml,fno-parameter-iri"
SDM="KGC_BENCH_PYTHONPATH_SDM_RDFIZER=$B/engines/sdm-rdfizer-patched KGC_BENCH_PATCHES=base-iri,join-term-maps,postgres-port,natural-datatypes,language-map-reference,reference-iri"
ROCK="KGC_BENCH_PIN_ROCKETRML_VERSION=3.0.0+patched KGC_BENCH_PATCHES=join-empty-values,join-duplicates,double-lexical-form,stream-nquads,graph-maps,multiple-classes"
patched() {  # patched <engine> <envs> <workload> <scales...>
  local e=$1 envs=$2 w=$3; shift 3
  plog "patched start engine=$e workload=$w scales=$*"
  env $envs KGC_BENCH_RESULTS=$B/results/patched/$e/iot-$ID KGC_BENCH_REFERENCE_RESULTS=$B/results \
    python -m harness.perf --workloads $w --scales "$@" --runs 5 --timeout-at 1000=3600 \
    --engines $e --campaign $ID >> $HOME/v2-patched-$e.log 2>&1
  plog "patched end engine=$e workload=$w exit=$?"
}
# 1. ours, GTFS 1-100 (references of the patched runs)
ENGINES="$OURS" STEPS=perf-gtfs GTFS_SCALES="1 10 100" scripts/campaign.sh $ID > $HOME/v2-campaign.log 2>&1
# 2. patched, GTFS 1-100
patched flexrml "$FLEX" gtfs 1 10 100
patched sdm-rdfizer "$SDM" gtfs 1 10 100
patched rocketrml "$ROCK" gtfs 1 10
# 3. gtfs-inverted 1, 10: ours and the released engines, then the patched ones
plog "gtfs-inverted start"
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines $OURS morph-kgc morph-kgc-4p rmlmapper rpt sparql-anything burp rmlstreamer shexml \
  --campaign $ID > $HOME/v2-inverted.log 2>&1
plog "gtfs-inverted end exit=$?"
patched flexrml "$FLEX" gtfs-inverted 1 10
patched sdm-rdfizer "$SDM" gtfs-inverted 1 10
patched rocketrml "$ROCK" gtfs-inverted 1 10
# 4. ours, GTFS 1000, then the patched engines that finished at 100
ENGINES="$OURS" STEPS=perf-gtfs GTFS_SCALES="1 10 100 1000" scripts/campaign.sh $ID >> $HOME/v2-campaign.log 2>&1
patched flexrml "$FLEX" gtfs 1000
patched sdm-rdfizer "$SDM" gtfs 1000
plog "all-done"
