#!/bin/sh
# A/B measurement of the translator: A = the pinned rml2sparql-generate
# (third_party/; RML2SG_A=<dir> for another copy), B = a working copy
# (RML2SG_B, default ../rml-to-sparql-generate), run in the order A B B A
# (AB_ORDER="B" for a single pass) for each workload, on the translated-query engines
# (SPARQL-Generate and pysparql-generate), one run at a time, under the run
# limits of harness.perf. Results: results/translator-ab.csv (one line per
# run: variant, workload, scale, engine, status, wall, peak RSS, distinct
# triples, and the series A_REV..B_REV); the measurements of results/perf.csv are
# not touched.
#
#   scripts/ab_translator.sh flat-csv:1000 gtfs:10 ...
set -u
cd "$(dirname "$0")/.."
PY=${KGC_BENCH_PYTHON:-$HOME/.venvs/kgc-bench/bin/python}
A=${RML2SG_A:-$(pwd)/third_party/rml-to-sparql-generate}
B=${RML2SG_B:-../rml-to-sparql-generate}
ORDER=${AB_ORDER:-A B B A}
OUT=${AB_DIR:-results/tmp/ab}
CSV=results/translator-ab.csv
ENGINES=${ENGINES:-sg-java-translated pysparql-generate-translated}
A_REV=$(git -C "$A" rev-parse --short HEAD)$(git -C "$A" diff --quiet || echo "+dirty")
B_REV=$(git -C "$B" rev-parse --short HEAD)$(git -C "$B" diff --quiet || echo "+dirty")
[ -e "$CSV" ] || echo "date,variant,translator,workload,scale,engine,version,status,wall_s,rss_mb,triples,series" > "$CSV"
for ws in "$@"; do
    w=${ws%%:*}; s=${ws##*:}
    for v in $ORDER; do
        if [ "$v" = B ]; then export RML2SG_DIR="$B"; rev=$B_REV; else export RML2SG_DIR="$A"; rev=$A_REV; fi
        rm -rf "$OUT/$v"
        KGC_BENCH_RESULTS="$OUT/$v" "$PY" -m harness.perf --workloads "$w" --scales "$s" \
            --engines $ENGINES --runs 1 --no-check > "$OUT.$v.log" 2>&1
        "$PY" - "$OUT/$v/perf.csv" "$v" "$rev" "$CSV" "$A_REV..$B_REV" <<'PYEOF'
import csv, datetime, sys
src, v, rev, dst, series = sys.argv[1:6]
with open(dst, "a", newline="") as f:
    w = csv.writer(f)
    for r in csv.DictReader(open(src)):
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), v, rev, r["workload"],
                    r["scale"], r["engine"], r["version"].split(" + ")[0], r["status"], r["wall_s"],
                    r["rss_mb"], r["triples"], series])
        print(v, rev, r["workload"], r["scale"], r["engine"], r["status"], r["wall_s"], r["rss_mb"],
              r["triples"], flush=True)
PYEOF
        rm -rf "$OUT/$v/tmp"
    done
done
