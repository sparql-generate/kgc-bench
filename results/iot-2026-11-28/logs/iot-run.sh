#!/bin/bash
# On iot, as kgcbench: A/B of the 2.6.0 checks, then campaign 2026-11-27-table4 (GTFS 1-1000),
# then gtfs-inverted (1, 10). Unattended; progress in the public log.
set -u
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
export KGC_BENCH_PYSG_PYTHON=$HOME/.venvs/pysg/bin/python
. ~/.venvs/kgc-bench/bin/activate
plog() { echo "$(date -Iseconds) event=$*" >> $KGC_BENCH_PUBLIC_LOG; }
git config user.name >/dev/null || { git config user.name "kgc-bench campaign"; git config user.email "kgc-bench@localhost"; }
git pull -q
SKIP_PIP=1 ./scripts/fetch_engines.sh > /dev/null
./scripts/fetch_testcases.sh > /dev/null

# --- A/B: 2.5.0 + translator 5fa291a + pysparql-generate 0.2.0 (A) against the pins (B)
plog "ab-versions start A=sparql-generate-2.5.0 B=pinned"
A_JAR=engines/sparql-generate-2.5.0.jar
if [ ! -s $A_JAR ]; then
  curl -fsSL -o $A_JAR.part https://github.com/sparql-generate/sparql-generate/releases/download/v2.5.0/sparql-generate-2.5.0.jar
  echo "ea275f0bd1a0bf0169c7c913544478942280b5848dcd3643aed03a0a5f233dbd  $A_JAR.part" | sha256sum -c --quiet && mv $A_JAR.part $A_JAR
fi
A_RML2SG=$HOME/rml2sg-5fa291a
[ -d $A_RML2SG ] || git clone -q https://github.com/sparql-generate/rml-to-sparql-generate.git $A_RML2SG
git -C $A_RML2SG checkout -q 5fa291a
PYSG_COMMIT=8aab1719c7 ./scripts/build_pysparql_generate.sh > /dev/null
./scripts/build_pysparql_generate.sh > /dev/null        # back to the pinned export
AB_DIR=$HOME/ab-versions RUNS=5 A_JAR=sparql-generate-2.5.0.jar A_RML2SG=$A_RML2SG \
  A_PYSG=build/pysparql-generate-8aab1719c7 scripts/ab_versions.sh gtfs:1,10 nested-json:10,100 \
  > $HOME/ab-versions.log 2>&1
plog "ab-versions end exit=$?"

# --- campaign 2026-11-27-table4
export ENGINES="sg-java sg-java-translated pysparql-generate pysparql-generate-translated morph-kgc morph-kgc-4p rmlmapper sdm-rdfizer rpt sparql-anything rocketrml flexrml burp rmlstreamer shexml"
export STEPS="perf-gtfs" GTFS_SCALES="1 10 100 1000" RUNS=5 LIMIT_TIME_S_AT="1000=3600"
export QUIET_LOAD=1.5 QUIET_WAIT=3600
scripts/campaign.sh 2026-11-27-table4 > $HOME/campaign.log 2>&1
plog "campaign-script end exit=$?"

# --- gtfs-inverted, same engines and limits, same campaign
plog "gtfs-inverted start scales=1,10"
python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 --engines $ENGINES \
  --campaign 2026-11-27-table4 > $HOME/gtfs-inverted.log 2>&1
plog "gtfs-inverted end exit=$?"
plog "all-done"
