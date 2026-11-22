#!/bin/sh
# Builds the SPARQL-Generate executable JAR from a sibling working copy
# (default ../sparql-generate), WITHOUT touching it: the checked-out commit is
# cloned into build/, optionally patched with patches/*.patch, and built there
# with its own local Maven repository.
#
#   scripts/build_sparql_generate.sh            -> engines/sparql-generate-<sha>.jar
#   scripts/build_sparql_generate.sh --patched  -> engines/sparql-generate-<sha>+p<digest>.jar
#     (patches/*.patch applied: fixes proposed upstream, see README)
#
# The JAR name records the commit; engines/sparql-generate-head[+patches].jar
# is a symlink to the last build, which is what the harness runs by default.
# Uncommitted changes of the working copy are NOT included (only HEAD is built).
set -e
cd "$(dirname "$0")/.."
. ./versions.env
SRC=${SPARQL_GENERATE_SRC:-../sparql-generate}
PATCHED=""
LINK=sparql-generate-head.jar
if [ "${1:-}" = "--patched" ]; then
    # the name records which patches: a digest of their content
    PATCHED="+p$(cat patches/*.patch | sha1sum | cut -c1-8)"
    LINK=sparql-generate-head+patches.jar
fi
SHA=$(git -C "$SRC" rev-parse --short=10 HEAD)
BRANCH=$(git -C "$SRC" rev-parse --abbrev-ref HEAD)
OUT="engines/sparql-generate-$SHA$PATCHED.jar"
mkdir -p build engines
if [ -s "$OUT" ]; then
    echo "$OUT already built"
else
    W="build/sparql-generate-$SHA$PATCHED"
    rm -rf "$W"
    git clone --quiet "$SRC" "$W"
    git -C "$W" checkout --quiet "$SHA"
    if [ -n "$PATCHED" ]; then
        for p in patches/*.patch; do
            echo "applying $p"
            git -C "$W" apply --whitespace=nowarn "$PWD/$p"
        done
    fi
    JAVA_HOME="$JAVA_HOME_BUILD" mvn -f "$W/sparql-generate-parent/pom.xml" -q \
        -DskipTests -Drat.skip=true -Dmaven.javadoc.skip=true \
        -Dmaven.repo.local="$PWD/build/m2" package
    cp "$W/sparql-generate-all/target/sparql-generate.jar" "$OUT"
    echo "$BRANCH $SHA$PATCHED" > "$OUT.txt"
fi
ln -sf "$(basename "$OUT")" "engines/$LINK"
cp "$OUT.txt" "engines/$LINK.txt"
echo "engines/$LINK -> $OUT ($BRANCH)"
