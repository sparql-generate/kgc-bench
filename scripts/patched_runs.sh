#!/bin/sh
# harness.perf on workloads and scales, one engine at a time (one harness process per
# engine, so that an engine built with the patches proposed upstream gets the environment of
# its patches only). An engine whose patched build is not in engines/ (scripts/patches/build.sh,
# on the branch patched-engines) runs as released, and the script says so.
#
#   scripts/patched_runs.sh "<workloads>" "<scales>" ["<engines>"]
#   scripts/patched_runs.sh "gtfs" "1 10"
#
# Environment (with defaults):
#   KGC_BENCH_RESULTS   results/runs-<date>          the results directory
#   KGC_BENCH_SLICE     agents.slice                 the systemd slice of the runs
#   KGC_BENCH_PYSG_PYTHON ~/.venvs/pysg/bin/python   the Python of pysparql-generate
#   RUNS (1) TIMEOUT (600) MEM_CAP (12G)             harness.perf options
#   EXTRA                                             more harness.perf options
#   PY                  ~/.venvs/kgc-bench/bin/python the Python of the harness
set -e
workloads=$1; scales=$2
engines=${3:-"morph-kgc flexrml sdm-rdfizer burp rmlmapper sg-java-translated pysparql-generate-translated"}
cd "$(dirname "$0")/.."
: "${KGC_BENCH_RESULTS:=$PWD/results/runs-$(date +%F)}"
: "${KGC_BENCH_SLICE:=agents.slice}"
: "${KGC_BENCH_PYSG_PYTHON:=$HOME/.venvs/pysg/bin/python}"
: "${JAVA_HOME:=/usr/lib/jvm/java-21-openjdk-amd64}"
export KGC_BENCH_RESULTS KGC_BENCH_SLICE KGC_BENCH_PYSG_PYTHON JAVA_HOME
PY=${PY:-$HOME/.venvs/kgc-bench/bin/python}
patches() { # the subjects of the patches of an engine, comma-separated (as build.sh)
  for p in scripts/patches/$1/*.patch; do sed -n 's/^Subject: \[PATCH[^]]*\] //p' "$p" | head -1; done | paste -sd, -
}
released() { echo "$1: no patched build in engines/, run as released" >&2; }
for e in $engines; do
  unset KGC_BENCH_PATCHES KGC_BENCH_PYTHONPATH_MORPH_KGC KGC_BENCH_PYTHONPATH_SDM_RDFIZER \
    KGC_BENCH_PIN_FLEXRML_VERSION KGC_BENCH_PIN_BURP_VERSION KGC_BENCH_PIN_RMLMAPPER_VERSION
  . ./versions.env
  case $e in
  morph-kgc)
    if [ -d engines/morph-kgc-patched ] && [ -d scripts/patches/morph-kgc ]; then
      export KGC_BENCH_PYTHONPATH_MORPH_KGC=$PWD/engines/morph-kgc-patched
      export KGC_BENCH_PATCHES="main 979ade7, $(patches morph-kgc)"
    else released $e; fi ;;
  sdm-rdfizer)
    if [ -d engines/sdm-rdfizer-patched ] && [ -d scripts/patches/sdm-rdfizer ]; then
      export KGC_BENCH_PYTHONPATH_SDM_RDFIZER=$PWD/engines/sdm-rdfizer-patched
      export KGC_BENCH_PATCHES="$(patches sdm-rdfizer)"
    else released $e; fi ;;
  flexrml)
    if [ -e "engines/flexrml-$FLEXRML_VERSION+patched" ]; then
      export KGC_BENCH_PIN_FLEXRML_VERSION=$FLEXRML_VERSION+patched KGC_BENCH_PATCHES="$(patches flexrml)"
    else released $e; fi ;;
  burp)
    if ls engines/ | grep -q "^burp-$BURP_VERSION+patched"; then
      export KGC_BENCH_PIN_BURP_VERSION=$BURP_VERSION+patched KGC_BENCH_PATCHES="$(patches burp)"
    else released $e; fi ;;
  rmlmapper)
    if [ -e engines/rmlmapper-development-86e961d7+patched.jar ]; then
      export KGC_BENCH_PIN_RMLMAPPER_VERSION=development-86e961d7+patched
      export KGC_BENCH_PATCHES="$(patches rmlmapper)"
    else released $e; fi ;;
  esac
  echo "== $e ($(date +%T))"
  # shellcheck disable=SC2086
  $PY -m harness.perf --workloads $workloads --scales $scales --engines "$e" \
    --runs "${RUNS:-1}" --timeout "${TIMEOUT:-600}" --mem-cap "${MEM_CAP:-12G}" $EXTRA \
    2>&1 | grep -E "^==|^  [a-z]|check" || true
done
