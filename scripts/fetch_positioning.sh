#!/bin/sh
# Fetches the engines of the positioning scenarios (positioning/), pinned in
# versions.env: Apache Jena (the plain ARQ command line), Comunica (npm, into
# engines/comunica), and checks the Python ones (rdflib, pyoxigraph).
set -e
cd "$(dirname "$0")/.."
. ./versions.env
mkdir -p engines
if [ ! -x "engines/apache-jena-$JENA_VERSION/bin/sparql" ]; then
    echo "downloading Apache Jena $JENA_VERSION"
    curl -sSfL -o "engines/apache-jena-$JENA_VERSION.tar.gz" "$JENA_URL"
    echo "$JENA_SHA512  engines/apache-jena-$JENA_VERSION.tar.gz" | sha512sum -c --quiet
    tar -xzf "engines/apache-jena-$JENA_VERSION.tar.gz" -C engines
    rm "engines/apache-jena-$JENA_VERSION.tar.gz"
fi
echo "engines/apache-jena-$JENA_VERSION"
if [ ! -x engines/comunica/node_modules/.bin/comunica-sparql ]; then
    echo "installing Comunica $COMUNICA_VERSION"
    npm install --silent --no-audit --no-fund --prefix engines/comunica \
        "@comunica/query-sparql@$COMUNICA_VERSION"
fi
echo "engines/comunica $(engines/comunica/node_modules/.bin/comunica-sparql --version 2>/dev/null | head -1)"
python -c "import rdflib, pyoxigraph; print('rdflib', rdflib.__version__, '- pyoxigraph', pyoxigraph.__version__)"
