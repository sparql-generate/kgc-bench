#!/bin/bash
# Campaign 2026-11-28-v3: the latest versions (Maxime, 2026-11-28): SPARQL-Generate 2.6.3,
# rml-to-sparql-generate 0.5.2, pysparql-generate 0.4.2 (kgc-bench main faa8547 or later),
# GTFS 1-1000 and gtfs-feeds K = 10, 100, 1000; RMLMapper with five patches (#288), GTFS 1-1000.
set -u
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
ID=2026-11-28-v3
plog() { echo "$(date -Iseconds) campaign=$ID event=$*" >> $KGC_BENCH_PUBLIC_LOG; }
git fetch -q origin && git checkout -q origin/main -- harness scripts versions.env workloads conformance tests README.md REPRODUCE.md 2>/dev/null
git checkout -q origin/main -- harness scripts versions.env workloads || { plog "checkout-failed"; exit 1; }
SKIP_PIP=1 ./scripts/fetch_engines.sh > $HOME/run4-fetch.log 2>&1
./scripts/fetch_testcases.sh >> $HOME/run4-fetch.log 2>&1
$KGC_BENCH_PYSG_PYTHON -m pip install -q "pysparql-generate[sql]==0.4.2" >> $HOME/run4-fetch.log 2>&1
$KGC_BENCH_PYSG_PYTHON -m pip uninstall -q -y pysparql-generate >> $HOME/run4-fetch.log 2>&1
./scripts/build_pysparql_generate.sh >> $HOME/run4-fetch.log 2>&1 || { plog "pysg-build-failed"; exit 1; }
V=$(grep -E '^(SPARQL_GENERATE_VERSION|RML2SG_COMMIT|PYSPARQL_GENERATE_COMMIT)=' versions.env | tr '\n' ' ')
[ -s engines/sparql-generate-2.6.3.jar ] || { plog "sg-2.6.3-jar-missing"; exit 1; }
[ "$(cat engines/pysparql-generate/COMMIT)" = "$(sed -n 's/^PYSPARQL_GENERATE_COMMIT=//p' versions.env)" ] || { plog "pysg-wrong-export"; exit 1; }
git -C third_party/rml-to-sparql-generate rev-parse HEAD | grep -q "^$(sed -n 's/^RML2SG_COMMIT=//p' versions.env | cut -c1-7)" || { plog "translator-wrong-commit"; exit 1; }
[ -d $HOME/kgc-bench-feeds/harness ] || { plog "feeds-code-missing"; exit 1; }
plog "start versions=$V"
# gtfs-feeds (fiche bench/204, variant 1): K feeds of GTFS-Madrid-Bench scale 1, the official
# mapping once per feed; code of kgc-bench branch iot-feeds (rml-weaknesses + main f9e7790)
# in ~/kgc-bench-feeds, engines and data shared with ~/kgc-bench.
F=$HOME/kgc-bench-feeds; FR=$B/results/feeds-$ID
FLEX="KGC_BENCH_PIN_FLEXRML_VERSION=3.1.0+patched KGC_BENCH_PATCHES=no-natural-datatype-for-csv-xml,fno-parameter-iri"
SDM="KGC_BENCH_PYTHONPATH_SDM_RDFIZER=$B/engines/sdm-rdfizer-patched KGC_BENCH_PATCHES=base-iri,join-term-maps,postgres-port,natural-datatypes,language-map-reference,reference-iri"
feeds() {  # feeds <scales...>
  ( cd $F && KGC_BENCH_RESULTS=$FR python -m harness.perf --workloads gtfs-feeds --scales "$@" --runs 5 \
      --timeout-at 1000=3600 --engines sg-java sg-java-translated pysparql-generate pysparql-generate-translated morph-kgc rpt \
      --campaign $ID >> $HOME/run4-feeds.log 2>&1
    for e in flexrml sdm-rdfizer; do
      case $e in flexrml) envs=$FLEX;; sdm-rdfizer) envs=$SDM;; esac
      env $envs KGC_BENCH_RESULTS=$FR/patched/$e KGC_BENCH_REFERENCE_RESULTS=$FR python -m harness.perf --workloads gtfs-feeds \
        --scales "$@" --runs 5 --timeout-at 1000=3600 --engines $e --campaign $ID >> $HOME/run4-feeds.log 2>&1
    done )
  plog "gtfs-feeds end scales=$*"
}
OURS="sg-java sg-java-translated pysparql-generate pysparql-generate-translated"
feeds 10 100
python -m harness.perf --workloads gtfs --scales 1 10 100 1000 --runs 5 --timeout-at 1000=3600 \
  --engines $OURS --campaign $ID > $HOME/run4-gtfs.log 2>&1
plog "gtfs end exit=$?"
feeds 1000
env KGC_BENCH_PIN_RMLMAPPER_VERSION=development-86e961d7+patched5 \
  KGC_BENCH_PATCHES=natural-datatypes-json,json-bracket-references,target-compression,join-term-maps,self-join-child-subject \
  KGC_BENCH_RESULTS=$B/results/patched/rmlmapper/iot-$ID KGC_BENCH_REFERENCE_RESULTS=$B/results \
  python -m harness.perf --workloads gtfs --scales 1 10 100 1000 --runs 5 --timeout-at 1000=3600 \
  --engines rmlmapper --campaign $ID > $HOME/run4-rmlmapper.log 2>&1
plog "rmlmapper5 end exit=$?"
plog all-done
