#!/bin/sh
# Downloads the KGCW Challenge 2024 archive (4.5 GB, Zenodo record 10973433,
# pinned in versions.env) into data/kgcw-2024/ and unpacks the tasks the
# benchmark runs (the CSV parameter tasks: joins, duplicates, empty values,
# mappings, properties, records). Not versioned here.
set -e
cd "$(dirname "$0")/.."
. ./versions.env
mkdir -p data/kgcw-2024
A=data/kgcw-2024/challenge.tar.gz
if [ "$(stat -c %s "$A" 2>/dev/null || echo 0)" != "$KGCW_2024_SIZE" ]; then
    curl -sSfL -C - -o "$A" "$KGCW_2024_URL"
fi
if [ ! -d data/kgcw-2024/eswc-kgc-challenge-2024 ]; then
    tar -xzf "$A" -C data/kgcw-2024
fi
ls data/kgcw-2024/eswc-kgc-challenge-2024
