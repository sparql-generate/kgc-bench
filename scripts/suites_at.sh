#!/bin/sh
# The seven test suites as they were on a date: for each suite, the last commit of
# its default branch before DATE (never after the commit pinned in versions.env),
# exported into DEST/<suite> (the layout of third_party/), with DEST/SUITES.txt
# listing the commits. For measuring an engine against the suites of its release
# date: KGC_BENCH_THIRD_PARTY=DEST python -m harness.conformance ...
#
#   scripts/suites_at.sh 2026-05-10 /tmp/suites-2026-05-10
#
# Clones are kept in KGC_BENCH_SUITE_CACHE (default ~/.cache/kgc-bench/suites);
# third_party/ is not touched.
set -e
[ $# -eq 2 ] || { echo "usage: $0 DATE DEST" >&2; exit 2; }
date=$1; dest=$2
cd "$(dirname "$0")/.."
. ./versions.env
cache=${KGC_BENCH_SUITE_CACHE:-$HOME/.cache/kgc-bench/suites}
mkdir -p "$cache" "$dest"
: > "$dest/SUITES.txt"
at() { # suite repo pinned-commit
    c="$cache/$1"
    [ -d "$c/.git" ] || git clone --quiet "$2" "$c"
    git -C "$c" cat-file -e "$3^{commit}" 2>/dev/null || git -C "$c" fetch --quiet origin
    commit=$(git -C "$c" rev-list -n 1 --first-parent --before="$date 23:59:59" "$3")
    if [ -z "$commit" ]; then
        echo "$1 - (no commit before $date)" >> "$dest/SUITES.txt"
        return
    fi
    rm -rf "${dest:?}/$1" && mkdir -p "$dest/$1"
    git -C "$c" archive "$commit" | tar -x -C "$dest/$1"
    echo "$1 $(git -C "$c" log -1 --format='%h %ad' --date=short "$commit")" >> "$dest/SUITES.txt"
}
at rml-test-cases "$RML_TEST_CASES_REPO" "$RML_TEST_CASES_COMMIT"
at rml-core "$RML_CORE_REPO" "$RML_CORE_COMMIT"
at rml-io "$RML_IO_REPO" "$RML_IO_COMMIT"
at rml-fnml "$RML_FNML_REPO" "$RML_FNML_COMMIT"
at rml-cc "$RML_CC_REPO" "$RML_CC_COMMIT"
at rml-star "$RML_STAR_REPO" "$RML_STAR_COMMIT"
at rml-lv "$RML_LV_REPO" "$RML_LV_COMMIT"
cat "$dest/SUITES.txt"
