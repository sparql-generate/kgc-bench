#!/bin/sh
# GTFS-Madrid-Bench (CSV distribution): fetches the benchmark (pinned) into
# third_party/gtfs-bench and puts the data of scale N in data/gtfs/N/.
#
#   scripts/gtfs_data.sh N                 generate with the benchmark's own
#                                          generator (VIG over the Madrid MySQL
#                                          dump, in Docker)
#   scripts/gtfs_data.sh N --from DIR      import CSV files generated before
#                                          (the 10 files of the CSV distribution)
set -e
cd "$(dirname "$0")/.."
. ./versions.env
N=${1:?scale}
if [ ! -d third_party/gtfs-bench/.git ]; then
    git clone --quiet "$GTFS_BENCH_REPO" third_party/gtfs-bench
fi
git -C third_party/gtfs-bench checkout --quiet "$GTFS_BENCH_COMMIT"
mkdir -p "data/gtfs/$N"
if [ "${2:-}" = "--from" ]; then
    cp "${3:?directory}"/*.csv "data/gtfs/$N/"
else
    # the benchmark's generator: a MySQL 5.7 with the Madrid dump, then VIG
    docker rm -f kgc-bench-gtfs-mysql >/dev/null 2>&1 || true
    docker run -d --name kgc-bench-gtfs-mysql -e MYSQL_ROOT_PASSWORD=root \
        -e MYSQL_DATABASE=gtfs -e MYSQL_USER=oeg -e MYSQL_PASSWORD=oeg \
        -p 127.0.0.1:3306:3306 \
        -v "$PWD/third_party/gtfs-bench/generation/mysql_data:/docker-entrypoint-initdb.d:ro" \
        mysql:5.7
    until docker exec kgc-bench-gtfs-mysql mysql -uoeg -poeg gtfs -e 'select 1' >/dev/null 2>&1; do sleep 5; done
    (cd third_party/gtfs-bench/generation && ./generate.sh "$N")
    cp third_party/gtfs-bench/generation/resources/csvs/*.csv "data/gtfs/$N/"
    docker rm -f kgc-bench-gtfs-mysql >/dev/null
fi
ls -la "data/gtfs/$N" | tail -n +2
