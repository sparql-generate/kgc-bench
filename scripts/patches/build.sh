#!/bin/sh
# Build an RML engine with the patches proposed upstream (scripts/patches/<engine>/,
# git format-patch files), into engines/ under a name of its own, and print the
# environment that points the harness at it:
#
#   scripts/patches/build.sh <engine> [workdir]
#   eval "$(scripts/patches/build.sh flexrml)"; scripts/patches/measure.sh flexrml patched
#
# Each engine is cloned at the commit the patches were written on (below), the
# patches applied with git am, then built as its project builds it. Never the
# published results of a release: the version column says "[patches: ...]".
# Heavy builds run under scripts/capped.sh; -j / -T are kept low (shared machine).
set -e
engine=$1
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
work=${2:-${TMPDIR:-/tmp}/kgc-bench-patched-src}
. "$root/versions.env"
mkdir -p "$work"
src=$work/$engine
patches=$here/$engine

clone() { # repo commit
  rm -rf "$src"
  git clone -q "$1" "$src"
  git -C "$src" checkout -q "$2"
  git -C "$src" -c user.name=kgc-bench -c user.email=kgc-bench@invalid am -q "$patches"/*.patch
}
names() { # the subjects of the patches, comma-separated
  for p in "$patches"/*.patch; do sed -n 's/^Subject: \[PATCH[^]]*\] //p' "$p" | head -1; done | paste -sd, -
}

case $engine in
morph-kgc)
  clone https://github.com/morph-kgc/morph-kgc.git 979ade7
  dest=$root/engines/morph-kgc-patched
  rm -rf "$dest"
  python -m pip install -q --target "$dest" "$src" >&2
  echo "export KGC_BENCH_PYTHONPATH_MORPH_KGC=$dest"
  echo "export KGC_BENCH_PATCHES='main 979ade7, $(names)'" ;;
sdm-rdfizer)
  clone https://github.com/SDM-TIB/SDM-RDFizer.git b8c71fd
  dest=$root/engines/sdm-rdfizer-patched
  rm -rf "$dest"
  # the release's metadata (version), the patched package over it; its
  # dependencies are those of the harness's environment
  python -m pip install -q --no-deps --target "$dest" "rdfizer==$SDM_RDFIZER_VERSION" >&2
  rm -rf "$dest/rdfizer"
  cp -r "$src/rdfizer/rdfizer" "$dest/rdfizer"
  echo "export KGC_BENCH_PYTHONPATH_SDM_RDFIZER=$dest"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
rpt)
  # R2-RML-Toolkit (develop) holds the RML code of RPT; its SNAPSHOT dependencies
  # are not all published, so the patched class is compiled against the release
  # jar and replaces its own in a copy of it
  clone https://github.com/Scaseco/R2-RML-Toolkit.git b640973
  jar=$root/engines/rpt-$RPT_VERSION.jar
  dest=$root/engines/rpt-$RPT_VERSION+patched.jar
  classes=$work/rpt-classes
  rm -rf "$classes"; mkdir -p "$classes"
  "$JAVA_HOME_BUILD/bin/javac" -nowarn --release 17 -d "$classes" -cp "$jar" \
    "$src/rml-jena-arq/src/main/java/org/aksw/rml/jena/service/InitRmlService.java" \
    "$src/r2rml-jena-arq/src/main/java/org/aksw/r2rml/jena/arq/impl/TriplesMapProcessorR2rml.java" \
    "$src/r2rml-jena-arq/src/main/java/org/aksw/r2rml/jena/arq/impl/R2rmlImporterLib.java"
  cp "$jar" "$dest"
  (cd "$classes" && "$JAVA_HOME_BUILD/bin/jar" uf "$dest" org/aksw/rml/jena/service/*.class \
    org/aksw/r2rml/jena/arq/impl/TriplesMapProcessorR2rml*.class org/aksw/r2rml/jena/arq/impl/R2rmlImporterLib*.class)
  echo "export KGC_BENCH_PIN_RPT_VERSION=$RPT_VERSION+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
flexrml)
  # dependencies by vcpkg (manifest mode), as its README builds it
  clone https://github.com/wintechis/flex-rml.git "$FLEXRML_VERSION"
  [ -x "$work/vcpkg/vcpkg" ] || { git clone -q https://github.com/microsoft/vcpkg.git "$work/vcpkg"; "$work/vcpkg/bootstrap-vcpkg.sh" -disableMetrics >&2; }
  (cd "$src" && "$root/scripts/capped.sh" "$work/vcpkg/vcpkg" install --triplet x64-linux >&2 &&
   cmake --preset default >&2 && "$root/scripts/capped.sh" cmake --build build/default -j3 >&2)
  cp "$src/flexrml" "$root/engines/flexrml-$FLEXRML_VERSION+patched"
  echo "export KGC_BENCH_PIN_FLEXRML_VERSION=$FLEXRML_VERSION+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
rmlmapper)
  clone https://github.com/RMLio/rmlmapper-java.git 86e961d7
  (cd "$src" && JAVA_HOME=$JAVA_HOME_BUILD "$root/scripts/capped.sh" mvn -B -q -T 1 -DskipTests package >&2)
  cp "$src"/target/rmlmapper-*-all.jar "$root/engines/rmlmapper-development-86e961d7+patched.jar"
  echo "export KGC_BENCH_PIN_RMLMAPPER_VERSION=development-86e961d7+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
burp)
  # the shaded jar of the release (profile deploy, as the release workflow)
  clone https://github.com/kg-construct/BURP.git 906bb5a
  (cd "$src" && JAVA_HOME=$JAVA_HOME_BUILD "$root/scripts/capped.sh" mvn -B -q -T 1 -DskipTests -Pdeploy -Dgpg.skip package >&2)
  cp "$src/target/burp.jar" "$root/engines/burp-$BURP_VERSION+patched.jar"
  echo "export KGC_BENCH_PIN_BURP_VERSION=$BURP_VERSION+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
rmlstreamer)
  # the stand-alone jar (profile stand-alone, as its README builds it), on JDK 11
  clone https://github.com/RMLio/RMLStreamer.git 1f4dbad
  (cd "$src" && JAVA_HOME=$JAVA_HOME_RMLSTREAMER "$root/scripts/capped.sh" mvn -B -q -T 1 -DskipTests -P stand-alone package >&2)
  cp "$src"/target/RMLStreamer-v*-SNAPSHOT.jar "$root/engines/RMLStreamer-$RMLSTREAMER_VERSION+patched-standalone.jar"
  echo "export KGC_BENCH_PIN_RMLSTREAMER_VERSION=$RMLSTREAMER_VERSION+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
rocketrml)
  # the npm installation of the release (its locked dependency tree), the
  # patches applied to its copy of RocketRML (the release is the tag 3.0.0)
  dest=$root/engines/rocketrml-$ROCKETRML_VERSION+patched
  rm -rf "$dest"
  cp -a "$(readlink -f "$root/engines/rocketrml-$ROCKETRML_VERSION")" "$dest"
  # the npm package has src/ only, not the tests of the patches: their src/ hunks
  for p in "$patches"/*.patch; do
    python3 -c 'import re, sys; print("".join(d for d in re.split(r"(?m)^(?=diff --git )", open(sys.argv[1]).read()) if d.startswith("diff --git a/src/")))' "$p" \
      | patch -s -p1 -d "$dest/node_modules/rocketrml"
  done
  echo "export KGC_BENCH_PIN_ROCKETRML_VERSION=$ROCKETRML_VERSION+patched"
  echo "export KGC_BENCH_PATCHES='$(names)'" ;;
*)
  echo "unknown engine: $engine" >&2; exit 2 ;;
esac
