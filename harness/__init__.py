"""kgc-bench harness: conformance (RQ1) and performance (RQ3) of
SPARQL-Generate against RML engines and SPARQL Anything.

Every module is run from the repository root as ``python -m harness.<module>``.
This package only fixes paths and reads the pins of ``versions.env``.
"""

import os
import shutil

HARNESS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HARNESS)
# KGC_BENCH_THIRD_PARTY: another directory of test suites (the same layout), e.g.
# the suites as they were at an engine's release date (scripts/suites_at.sh)
THIRD_PARTY = os.path.abspath(os.environ.get("KGC_BENCH_THIRD_PARTY")
                              or os.path.join(ROOT, "third_party"))
ENGINES = os.path.join(ROOT, "engines")
DATA = os.path.join(ROOT, "data")
# KGC_BENCH_RESULTS: another results directory (a dry run, a test)
RESULTS = os.path.abspath(os.environ.get("KGC_BENCH_RESULTS") or os.path.join(ROOT, "results"))
BUILD = os.path.join(ROOT, "build")
HAND = os.path.join(ROOT, "conformance", "hand")

SUITES = {
    # suite name -> directory of the test cases
    "rml-test-cases": os.path.join(THIRD_PARTY, "rml-test-cases", "test-cases"),
    # its PostgreSQL and MySQL tracks, on local databases (harness.database, Docker)
    "rml-test-cases-sql": os.path.join(THIRD_PARTY, "rml-test-cases", "test-cases"),
    "rml-core": os.path.join(THIRD_PARTY, "rml-core", "test-cases"),
    # the test cases of the RML modules (W3C KG-Construct CG)
    "rml-io": os.path.join(THIRD_PARTY, "rml-io", "test-cases"),
    "rml-fnml": os.path.join(THIRD_PARTY, "rml-fnml", "test-cases"),
    "rml-cc": os.path.join(THIRD_PARTY, "rml-cc", "test-cases"),
    "rml-star": os.path.join(THIRD_PARTY, "rml-star", "test-cases"),
    "rml-lv": os.path.join(THIRD_PARTY, "rml-lv", "test-cases"),
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


# KGC_BENCH_PIN_<KEY>=<value> overrides the pin KEY of versions.env for one run,
# to measure another version of an engine (installed under engines/ by its
# usual name) without changing the pins; the version recorded with each
# result row is the overriding one.
PIN_OVERRIDE = "KGC_BENCH_PIN_"


def apply_overrides(pins, environ=os.environ):
    """pins, with the values of the KGC_BENCH_PIN_<KEY> variables of environ."""
    out = dict(pins)
    for k, v in environ.items():
        if k.startswith(PIN_OVERRIDE) and k[len(PIN_OVERRIDE):]:
            out[k[len(PIN_OVERRIDE):]] = v
    return out


VERSIONS = apply_overrides(read_versions())

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
