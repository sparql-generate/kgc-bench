"""kgc-bench harness: conformance (RQ1) and performance (RQ3) of
SPARQL-Generate against RML engines and SPARQL Anything.

Every module is run from the repository root as ``python -m harness.<module>``.
This package only fixes paths and reads the pins of ``versions.env``.
"""

import os
import shutil

HARNESS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HARNESS)
THIRD_PARTY = os.path.join(ROOT, "third_party")
ENGINES = os.path.join(ROOT, "engines")
DATA = os.path.join(ROOT, "data")
# KGC_BENCH_RESULTS: another results directory (a dry run, a test)
RESULTS = os.path.abspath(os.environ.get("KGC_BENCH_RESULTS") or os.path.join(ROOT, "results"))
BUILD = os.path.join(ROOT, "build")
HAND = os.path.join(ROOT, "conformance", "hand")

SUITES = {
    # suite name -> directory of the test cases
    "rml-test-cases": os.path.join(THIRD_PARTY, "rml-test-cases", "test-cases"),
    "rml-core": os.path.join(THIRD_PARTY, "rml-core", "test-cases"),
    # minimal cases of this benchmark (conformance/extra/README.md)
    "kgc-bench-extra": os.path.join(ROOT, "conformance", "extra"),
}


def read_versions(path=os.path.join(ROOT, "versions.env")):
    """The KEY=value pins of versions.env, as a dict."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


VERSIONS = read_versions()

# The RML -> SPARQL-Generate translator lives in its own repository, fetched
# at the commit pinned in versions.env (scripts/fetch_testcases.sh);
# RML2SG_DIR points the harness at a working copy instead.
RML2SG = os.environ.get(
    "RML2SG_DIR", os.path.join(THIRD_PARTY, "rml-to-sparql-generate"))
# the direct translation, without the rewritings of the optimised one
# (RML2SG_TAU_COMMIT): the engines *-translated-tau
RML2SG_TAU = os.environ.get(
    "RML2SG_TAU_DIR", os.path.join(THIRD_PARTY, "rml-to-sparql-generate-tau"))


def java(home_key="JAVA_HOME_BENCH"):
    """The java executable used for every Java engine."""
    home = os.environ.get(home_key) or VERSIONS.get(home_key)
    if home and os.path.exists(os.path.join(home, "bin", "java")):
        return os.path.join(home, "bin", "java")
    return shutil.which("java") or "java"
