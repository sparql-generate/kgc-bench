#!/bin/sh
# Downloads the released engines (pinned in versions.env) into engines/, and
# installs the Python engines into the active virtual environment.
# SPARQL-Generate built from source (KGC_BENCH_SG_JAR=head) is handled by
# build_sparql_generate.sh.
set -e
cd "$(dirname "$0")/.."
. ./versions.env
mkdir -p engines
get() { # file url
    if [ ! -s "engines/$1" ]; then
        echo "downloading $1"
        curl -sSfL -o "engines/$1.part" "$2" && mv "engines/$1.part" "engines/$1"
    fi
    echo "engines/$1 $(sha256sum "engines/$1" | cut -c1-16)"
}
get "sparql-generate-$SPARQL_GENERATE_VERSION.jar" "$SPARQL_GENERATE_URL"
echo "$SPARQL_GENERATE_SHA256  engines/sparql-generate-$SPARQL_GENERATE_VERSION.jar" | sha256sum -c --quiet
get "sparql-generate-$SPARQL_GENERATE_RELEASE.jar" "$SPARQL_GENERATE_RELEASE_URL"
get "rmlmapper-$RMLMAPPER_VERSION.jar" "$RMLMAPPER_URL"
get "sparql-anything-$SPARQL_ANYTHING_VERSION.jar" "$SPARQL_ANYTHING_URL"
get "rpt-$RPT_VERSION.jar" "$RPT_URL"
if [ "${SKIP_PIP:-}" != 1 ]; then
    python -m pip install --quiet -r requirements.txt
fi
