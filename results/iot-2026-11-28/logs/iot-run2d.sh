#!/bin/bash
# After kgc-bench-run2c: RMLMapper with five proposed patches (the four of
# scripts/patches/rmlmapper + MappingOptimizer child subject maps, RMLio/rmlmapper-java#288),
# GTFS 1-1000 and gtfs-inverted 1, 10.
set -u
while systemctl is-active --quiet kgc-bench-run2c; do sleep 60; done
export XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
B=~/kgc-bench; cd $B
export KGC_BENCH_MEM_CAP=24G KGC_BENCH_MEM_TOTAL=26G KGC_BENCH_CPUS=2-11
export KGC_BENCH_PUBLIC_LOG=/var/www/html/mqtt/benchmark.log KGC_BENCH_WORK=$HOME/work
. ~/.venvs/kgc-bench/bin/activate
plog() { echo "$(date -Iseconds) campaign=$1 event=$2" >> $KGC_BENCH_PUBLIC_LOG; }
export KGC_BENCH_PIN_RMLMAPPER_VERSION=development-86e961d7+patched5
export KGC_BENCH_PATCHES=natural-datatypes-json,json-bracket-references,target-compression,join-term-maps,self-join-child-subject
[ -s engines/rmlmapper-$KGC_BENCH_PIN_RMLMAPPER_VERSION.jar ] || { plog rmlmapper5 jar-missing; exit 1; }
plog 2026-11-27-v2 "rmlmapper5 start"
KGC_BENCH_RESULTS=$B/results/patched/rmlmapper/iot-2026-11-27-v2 KGC_BENCH_REFERENCE_RESULTS=$B/results \
  python -m harness.perf --workloads gtfs --scales 1 10 100 1000 --runs 5 --timeout-at 1000=3600 \
  --engines rmlmapper --campaign 2026-11-27-v2 > $HOME/rmlmapper5-gtfs.log 2>&1
KGC_BENCH_RESULTS=$B/results/patched/rmlmapper/iot-2026-11-27-inv KGC_BENCH_REFERENCE_RESULTS=$B/results \
  python -m harness.perf --workloads gtfs-inverted --scales 1 10 --runs 5 \
  --engines rmlmapper --campaign 2026-11-27-inv > $HOME/rmlmapper5-inv.log 2>&1
plog 2026-11-27-v2 "rmlmapper5 end"
