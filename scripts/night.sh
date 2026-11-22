#!/bin/sh
# Run a planned campaign at night, unattended (systemd user timer
# kgc-bench-night.timer, scripts/kgc-bench-night.{service,timer}).
#
#   scripts/night.sh               run the planned campaign, if any
#
# The plan is results/campaigns/planned.env (not versioned), a shell file that
# sets the campaign's variables, for example:
#
#   ID=2026-11-23-table3
#   ENGINES="sg-java sg-java-translated pysparql-generate pysparql-generate-translated morph-kgc rmlmapper sdm-rdfizer rpt sparql-anything"
#   STEPS="conformance perf-gtfs memory"
#   RUNS=5
#   PUSH=1                     push the commit of the results (default 1)
#
# Without a plan, nothing runs. The machine must be quiet: the campaign waits
# up to QUIET_WAIT (default 3600 s) for a 1-minute load under QUIET_LOAD
# (default 1.0), and otherwise does not start, and the next night tries again.
# A campaign interrupted by the morning (STOP_AT, default 07:30, local time)
# resumes the next night where it stopped (scripts/campaign.sh resumes). When
# the campaign finishes, the plan is renamed planned.env.done-<ID>.
set -u
cd "$(dirname "$0")/.."
PLAN=results/campaigns/planned.env
[ -f "$PLAN" ] || { echo "no planned campaign ($PLAN)"; exit 0; }
PUSH=1
set -a
. "./$PLAN"
set +a
: "${ID:?planned.env must set ID}"
export ENGINES STEPS="${STEPS:-}" RUNS="${RUNS:-5}"
export QUIET_LOAD="${QUIET_LOAD:-1.0}" QUIET_WAIT="${QUIET_WAIT:-3600}" QUIET_STRICT=1
STOP_AT=${STOP_AT:-07:30}

# stop at STOP_AT: the steps finished so far are kept, the rest resumes tomorrow
now=$(date +%s)
end=$(date -d "$STOP_AT" +%s)
[ "$end" -le "$now" ] && end=$(date -d "tomorrow $STOP_AT" +%s)
# its own process group: engines run in systemd scopes but stay in it, so
# that stopping the group stops them all
setsid scripts/campaign.sh "$ID" &
pid=$!
rc=
while kill -0 "$pid" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$end" ]; then
        kill -TERM -"$pid" 2>/dev/null
        sleep 60
        kill -KILL -"$pid" 2>/dev/null
        rc=124
        break
    fi
    sleep 30
done
if [ -z "$rc" ]; then wait "$pid"; rc=$?; fi
log=results/campaigns/$ID/campaign.log
if [ "$rc" = 0 ] && tail -1 "$log" | grep -q "campaign $ID finished"; then
    mv "$PLAN" "$PLAN.done-$ID"
    [ "$PUSH" = 1 ] && git push -q origin HEAD
    echo "campaign $ID finished"
elif [ "$rc" = 124 ]; then
    echo "campaign $ID stopped at $STOP_AT; it resumes next night"
    # the report and the commit of what was measured
    STEPS=none QUIET_STRICT=0 QUIET_WAIT=0 scripts/campaign.sh "$ID" >/dev/null 2>&1
else
    echo "campaign $ID: exit $rc (3: machine not quiet), see $log"
fi
exit 0
