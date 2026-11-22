#!/bin/sh
# One measurement campaign, meant for a quiet machine: conformance, the
# performance workloads, the report, and a commit of the results.
#
#   scripts/campaign.sh [ID]       ID: the campaign's name (default: today, YYYY-MM-DD)
#   DRY_RUN=1 scripts/campaign.sh  every step at its smallest size, one run, results in
#                                  results/dry-run/<ID>/, nothing committed
#
# Limits. Every run of every engine has the same limits: KGC_BENCH_MEM_CAP of
# memory (default 16G) and LIMIT_TIME_S of wall time (default 600 s). A run
# over a limit is stopped and recorded as not viable (OOM, DNF); it is never
# replayed, and the engine is not tried at a larger size.
#
# Resumption. Run the same command again after an interruption: a finished
# step is skipped, and inside a step a (workload, scale, engine) already
# measured in this campaign is not run again, whatever its status (a run cut
# short by the interruption is recorded "interrupted", not replayed). A step
# that failed is not retried either: remove its stamp results/campaigns/<ID>/
# <step>.failed to ask for it.
#
# Environment:
#   ENGINES              engines measured (default: pysparql-generate; e.g.
#                        "pysparql-generate sg-java sg-java-translated"); a
#                        *-translated engine runs the optimised translation (RML2SG_COMMIT), a
#                        *-translated-tau engine the direct one (RML2SG_TAU_COMMIT); the
#                        conformance step runs their base engines (sg-java,
#                        pysparql-generate), hand-written and translated
#   KGC_BENCH_MEM_CAP    memory limit of one run (default 16G)
#   KGC_BENCH_MEM_TOTAL  cap of all the campaign's processes together, the harness
#                        included (default 20G)
#   LIMIT_TIME_S         time limit of one run (default 600)
#   GTFS_1000=0          skip GTFS scale 1000
#   QUIET_LOAD, QUIET_WAIT  wait (at most QUIET_WAIT s, default 1800) for the 1-minute
#                        load average to fall under QUIET_LOAD (default 1.5) before
#                        starting; the campaign starts anyway, and says so in its log
#   KGC_BENCH_PYTHON     the Python of the harness (default ~/.venvs/kgc-bench/bin/python)
#
# Log: results/campaigns/<ID>/campaign.log (one line per step, with the load
# average, the available memory and the busiest processes), and one log per
# step next to it; the report and the commit are redone at every run.
#
# Memory: with a Java engine (sg-java, sg-java-translated, sg-java-translated-tau)
# in ENGINES, the smallest heap with which each completes flat-csv 1000
# (harness.memory, bisection over 64m ... 12g).
#
# Estimate for pysparql-generate alone: 1 to 2 h; for pysparql-generate and
# SPARQL-Generate, hand-written, optimised and direct translations (six engines), with GTFS_1000=0: 3 to
# 5 h (each scale over the time limit costs one run of 600 s, then the engine
# stops there). Peak memory: the memory limit for one run, KGC_BENCH_MEM_TOTAL
# in all. Every scope is in agents-kgcbench.slice, OOM score 1000.
set -u
export LC_ALL=C
cd "$(dirname "$0")/.."
ROOT=$PWD
PY=${KGC_BENCH_PYTHON:-$HOME/.venvs/kgc-bench/bin/python}
[ -x "$PY" ] || PY=python3
ID=${1:-$(date +%F)}
DRY=${DRY_RUN:-0}
ENGINES=${ENGINES:-pysparql-generate}
T=${LIMIT_TIME_S:-600}
export KGC_BENCH_CAMPAIGN="$ID"
export KGC_BENCH_MEM_CAP=${KGC_BENCH_MEM_CAP:-16G}
export KGC_BENCH_MEM_TOTAL=${KGC_BENCH_MEM_TOTAL:-20G}
if [ "$DRY" = 1 ]; then
    export KGC_BENCH_RESULTS="$ROOT/results/dry-run/$ID"
    DIR="$KGC_BENCH_RESULTS/campaign"
else
    DIR="$ROOT/results/campaigns/$ID"
fi
NEW=0
[ -d "$DIR" ] || NEW=1
mkdir -p "$DIR"
LOG="$DIR/campaign.log"

log() {
    echo "$(date '+%F %T') $*" | tee -a "$LOG"
}

machine() {
    load=$(cut -d' ' -f1-3 /proc/loadavg)
    avail=$(awk '/MemAvailable/ {printf "%.1f", $2 / 1048576}' /proc/meminfo)
    busy=$(ps -eo pcpu=,rss=,comm= --sort=-pcpu | awk 'NR <= 4 && $1 >= 10 {printf "%s(%d%%, %.1fG) ", $3, $1, $2 / 1048576}')
    echo "load $load, ${avail}G available, busy: ${busy:-none}"
}

# step NAME COMMAND...: run once per campaign; a failed step is not retried
# (its stamp NAME.failed says so) and does not stop the campaign
step() {
    name=$1
    shift
    if [ -e "$DIR/$name.done" ]; then
        log "skip  $name (done)"
        return 0
    fi
    if [ -e "$DIR/$name.failed" ]; then
        log "skip  $name (failed earlier, not retried: remove $DIR/$name.failed to retry)"
        return 0
    fi
    log "start $name [$(machine)]"
    t0=$(date +%s)
    if "$@" >> "$DIR/$name.log" 2>&1; then
        touch "$DIR/$name.done"
        log "done  $name in $(( $(date +%s) - t0 )) s [$(machine)]"
    else
        rc=$?
        touch "$DIR/$name.failed"
        log "FAIL  $name (exit $rc) in $(( $(date +%s) - t0 )) s, see $DIR/$name.log"
    fi
}

# the harness itself runs in the campaign's slice too (harness/sandbox.py)
harness() {
    scripts/capped.sh "$PY" -m "harness.$@"
}

log "campaign $ID (dry run: $DRY), engines: $ENGINES; limits $KGC_BENCH_MEM_CAP and $T s a run, $KGC_BENCH_MEM_TOTAL in all"
log "machine: $(machine)"
waited=0
while [ "$(awk -v q="${QUIET_LOAD:-1.5}" '{print ($1 < q)}' /proc/loadavg)" != 1 ] \
        && [ "$waited" -lt "${QUIET_WAIT:-1800}" ] && [ "$DRY" != 1 ]; do
    [ "$waited" = 0 ] && log "waiting for a quiet machine (load < ${QUIET_LOAD:-1.5})"
    sleep 60
    waited=$((waited + 60))
done
[ "$waited" -gt 0 ] && log "start after $waited s: $(machine)"

if [ "$NEW" = 1 ] && [ "$DRY" != 1 ]; then
    # outputs of earlier runs: not this campaign's, and they take disk space
    rm -rf results/tmp/perf
fi

# --- preparation: pinned engines, the pysparql-generate commit, test suites, data
step prepare sh -c '
    SKIP_PIP=1 ./scripts/fetch_engines.sh &&
    ./scripts/fetch_testcases.sh &&
    { [ -e engines/pysparql-generate ] || ./scripts/build_pysparql_generate.sh; } &&
    if [ "${GTFS_1000:-1}" = 1 ] && [ ! -d data/gtfs/1000 ] &&
            [ -d data/kgcw-2024/track2/gtfs-madrid-bench/scale_1000/data/shared ]; then
        mkdir -p data/gtfs/1000 &&
        ln -s "$PWD"/data/kgcw-2024/track2/gtfs-madrid-bench/scale_1000/data/shared/*.csv data/gtfs/1000/
    fi'

# --- RQ1: conformance (no timing), one case at a time, of the base engines
CONF=$(for e in $ENGINES; do case $e in sg-java*) echo sg-java ;; pysparql-generate*) echo pysparql-generate ;;
    *) echo "$e" ;; esac; done | sort -u | tr '\n' ' ')
if [ "$DRY" = 1 ]; then
    step conformance harness conformance --engines $CONF --jobs 1 --quiet \
        --only RMLTC0001a-CSV RMLTC0009a-JSON RMLTC0002e-XML RMLTC0012a-JSON
else
    step conformance harness conformance --engines $CONF --jobs 1 --quiet
fi

# --- RQ3: performance, one cold process per run, sequentially
if [ "$DRY" = 1 ]; then
    R="--engines $ENGINES --runs 1 --timeout $T"
    step perf-gtfs harness perf --workloads gtfs --scales 1 $R
    step perf-nested harness perf --workloads nested-json nested-xml --scales 1 $R
    step perf-flat harness perf --workloads flat-csv --scales 10 $R
else
    R="--engines $ENGINES --runs 3 --timeout $T"
    G="1 10 100"
    [ "${GTFS_1000:-1}" = 1 ] && G="$G 1000"
    step perf-gtfs harness perf --workloads gtfs --scales $G $R
    step perf-nested harness perf --workloads nested-json nested-xml --scales 1 10 100 $R
    step perf-flat harness perf --workloads flat-csv --scales 100 1000 $R
    # the KGCW 2024 tasks are RML mappings: only for engines that read them
    # (sg-java-translated); skipped quickly otherwise
    step perf-kgcw harness perf --workloads kgcw-records-100K kgcw-records-1M \
        kgcw-properties-1M-10 kgcw-duplicates-50 kgcw-empty-50 kgcw-mappings-15tm-1pom \
        kgcw-join-1-1-50 kgcw-join-1-N-50 kgcw-join-N-M-50 $R
fi

# --- memory: the smallest heap of each Java engine (SPARQL-Generate 2.3.0 or
# later: 2.2.4 swallowed an OutOfMemoryError and wrote a partial output)
JAVA=$(for e in $ENGINES; do case $e in sg-java|sg-java-translated|sg-java-translated-tau) echo "$e" ;;
    esac; done | tr '\n' ' ')
if [ -n "$JAVA" ]; then
    if [ "$DRY" = 1 ]; then MS=10; else MS=1000; fi
    step memory harness memory --workload flat-csv --scale $MS --engines $JAVA --timeout $T --campaign "$ID"
fi

# --- report and commit: every time (a resumed campaign adds results)
log "start report"
harness report >> "$DIR/report.log" 2>&1 && log "done  report" || log "FAIL  report"
if [ "$DRY" != 1 ]; then
    summary=$("$PY" -m harness.report --campaign-summary "$ID")
    cp "$LOG" "results/campaign-$ID.log"
    git add results/conformance.csv results/perf.csv results/perf-runs.csv results/machine.json \
        results/results.md "results/campaign-$ID.log"
    [ -e results/memory.csv ] && git add results/memory.csv
    if git diff --cached --quiet; then
        log "nothing new to commit"
    elif git commit -q -m "Campaign $ID: conformance and performance of $ENGINES

$summary

Run by scripts/campaign.sh $ID; limits $KGC_BENCH_MEM_CAP and $T s a run."; then
        log "committed $(git log --oneline -1)"
    else
        log "FAIL  commit"
    fi
fi
log "campaign $ID finished"
