#!/bin/sh
# Fetches the releases of the fidelity scenario (positioning/fidelity/releases.txt:
# file, URL, SHA-256) into engines/versions/, checksums verified. About 1.2 GB.
set -e
cd "$(dirname "$0")/.."
mkdir -p engines/versions
grep -v '^#' positioning/fidelity/releases.txt | while read -r f url sha; do
    [ -n "$f" ] || continue
    out="engines/versions/$f"
    if [ ! -s "$out" ]; then
        echo "downloading $f"
        curl -sSfL -o "$out.part" "$url" && mv "$out.part" "$out"
    fi
    echo "$sha  $out" | sha256sum -c --quiet
done
ls engines/versions
