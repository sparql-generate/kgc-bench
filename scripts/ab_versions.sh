#!/bin/sh
# A/B of two versions of SPARQL-Generate (Java and Python) and of the translator, in the
# order A B B A, on the engines sg-java, sg-java-translated, pysparql-generate and
# pysparql-generate-translated, under the run limits of harness.perf; results apart,
# in $AB_DIR/<variant><pass>/perf.csv (results/perf.csv untouched).
#
#   A_JAR=sparql-generate-2.5.0.jar A_RML2SG=<dir> A_PYSG=build/pysparql-generate-8aab1719c7 \
#   scripts/ab_versions.sh gtfs:1,10 nested-json:10,100
# B: the pinned versions (versions.env). RUNS (default 3), AB_DIR (default results/tmp/ab-versions).
set -u
cd "$(dirname "$0")/.."
PY=${KGC_BENCH_PYTHON:-$HOME/.venvs/kgc-bench/bin/python}
OUT=${AB_DIR:-results/tmp/ab-versions}
n=0
for v in A B B A; do
    n=$((n + 1))
    if [ "$v" = A ]; then
        J=$A_JAR; T=$A_RML2SG; P=$(cd "$A_PYSG" && pwd)
    else
        J=; T=$PWD/third_party/rml-to-sparql-generate; P=
    fi
    for ws in "$@"; do
        w=${ws%%:*}; s=$(echo "${ws#*:}" | tr ',' ' ')
        echo "== $v pass $n $w $s $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"
        KGC_BENCH_SG_JAR=$J RML2SG_DIR=$T KGC_BENCH_PYSG_DIR=$P KGC_BENCH_RESULTS=$OUT/$v$n \
            scripts/capped.sh "$PY" -m harness.perf --workloads "$w" --scales $s \
            --engines sg-java sg-java-translated pysparql-generate pysparql-generate-translated \
            --runs "${RUNS:-3}" --campaign "ab-$v$n"
    done
done
echo "== end $(date +%T)"
