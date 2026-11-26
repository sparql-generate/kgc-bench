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
# engines added on 2026-11-26, each checked against its pinned SHA-256
check() { # file sha256
    echo "$2  engines/$1" | sha256sum -c --quiet
}
get "flexrml-$FLEXRML_VERSION" "$FLEXRML_URL"
check "flexrml-$FLEXRML_VERSION" "$FLEXRML_SHA256"
chmod +x "engines/flexrml-$FLEXRML_VERSION"
get "burp-$BURP_VERSION.jar" "$BURP_URL"
check "burp-$BURP_VERSION.jar" "$BURP_SHA256"
get "RMLStreamer-$RMLSTREAMER_VERSION-standalone.jar" "$RMLSTREAMER_URL"
check "RMLStreamer-$RMLSTREAMER_VERSION-standalone.jar" "$RMLSTREAMER_SHA256"
get "ShExML-$SHEXML_VERSION.jar" "$SHEXML_URL"
check "ShExML-$SHEXML_VERSION.jar" "$SHEXML_SHA256"
# Node.js for RocketRML (official binary, checksum pinned)
N="node-v$NODE_VERSION-linux-x64"
if [ ! -x "engines/$N/bin/node" ]; then
    get "$N.tar.xz" "$NODE_URL"
    check "$N.tar.xz" "$NODE_SHA256"
    tar -xJf "engines/$N.tar.xz" -C engines && rm "engines/$N.tar.xz"
fi
# RocketRML: a Node.js library; npm ci installs the locked dependency tree (integrity
# hashes of scripts/rocketrml/package-lock.json); the wrapper scripts/rocketrml/rocketrml.js runs it
R="engines/rocketrml-$ROCKETRML_VERSION"
if [ ! -d "$R/node_modules/rocketrml" ]; then
    rm -rf "$R" && mkdir -p "$R"
    cp scripts/rocketrml/package.json scripts/rocketrml/package-lock.json "$R/"
    (cd "$R" && PATH="$PWD/../$N/bin:$PATH" npm ci --silent --no-audit --no-fund)
fi
# rdf-canonize (RDFC-1.0, the fingerprint of outputs with blank nodes): its npm tarball
# checked against the pinned SHA-256, then npm ci with the lockfile
C="engines/rdfc-$RDF_CANONIZE_VERSION"
if [ ! -d "$C/node_modules/rdf-canonize" ]; then
    get "rdf-canonize-$RDF_CANONIZE_VERSION.tgz" "$RDF_CANONIZE_URL"
    check "rdf-canonize-$RDF_CANONIZE_VERSION.tgz" "$RDF_CANONIZE_SHA256"
    rm -rf "$C" && mkdir -p "$C"
    cp scripts/rdfc/package.json scripts/rdfc/package-lock.json "$C/"
    (cd "$C" && PATH="$PWD/../$N/bin:$PATH" npm ci --silent --no-audit --no-fund)
    rm "engines/rdf-canonize-$RDF_CANONIZE_VERSION.tgz"
fi
if [ "${SKIP_PIP:-}" != 1 ]; then
    python -m pip install --quiet -r requirements.txt
fi
