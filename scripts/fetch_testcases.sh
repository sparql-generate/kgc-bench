#!/bin/sh
# Fetches the official RML test suites, pinned, into third_party/ (not
# versioned here: they keep their own licence).
#   - RMLio/rml-test-cases   (CSV, JSON, XML tracks of the RML/R2RML suite)
#   - kg-construct/rml-core  (the W3C KG-Construct CG RML-Core test cases)
# and the translator rml-to-sparql-generate, pinned likewise (optimised and direct translations).
set -e
cd "$(dirname "$0")/.."
. ./versions.env
mkdir -p third_party
fetch() { # dir repo commit
    if [ ! -d "third_party/$1/.git" ]; then
        git clone --quiet "$2" "third_party/$1"
    fi
    git -C "third_party/$1" cat-file -e "$3^{commit}" 2>/dev/null || git -C "third_party/$1" fetch --quiet origin
    git -C "third_party/$1" checkout --quiet "$3"
    echo "$1 at $(git -C "third_party/$1" log --oneline -1)"
}
fetch rml-test-cases "$RML_TEST_CASES_REPO" "$RML_TEST_CASES_COMMIT"
fetch rml-core "$RML_CORE_REPO" "$RML_CORE_COMMIT"
fetch rml-to-sparql-generate "$RML2SG_REPO" "$RML2SG_COMMIT"
fetch rml-to-sparql-generate-tau "$RML2SG_REPO" "$RML2SG_TAU_COMMIT"
