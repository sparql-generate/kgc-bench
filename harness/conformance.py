"""RQ1 — conformance of SPARQL-Generate to the official RML test suites,
judged by RDF dataset isomorphism with each case's expected output.

    python -m harness.conformance [--suites rml-test-cases rml-core]
                                  [--modes hand translated rml]
                                  [--engines sg-java sg-java-2.1.0 pysparql-generate rpt]
                                  [--only RMLTC0001a-CSV ...] [--jobs 2] [--mem-cap 16G]

Two ways for a SPARQL-Generate engine (sg-java, sg-java-2.1.0,
pysparql-generate) to solve a case, both reported:

hand        a query written by hand, conformance/hand/<suite>/<case>.rqg;
translated  the case's RML mapping translated by rml2sparql-generate (a
            SPARQL-Generate query, ../rml-to-sparql-generate), then the
            generated query run on the case's sources;

and one for an RML engine (rpt), the reference point:

rml         the engine runs the case's mapping itself.

Every engine process runs in a memory-capped scope (harness.sandbox).

Statuses:
    PASS   output isomorphic to the expected output.nq — or, for a case that
           expects an error, an error was raised (translated mode);
    N/A    translated mode, a case with graph maps whose default graph is
           isomorphic: GENERATE templates hold triples, not quads (the
           translator does not use GRAPH in templates yet);
    FAIL   output differs, or an error was raised (or not) unexpectedly;
    N/A    also, an invalid-mapping case in hand mode: there is no mapping to
           write a query for (see INVALID);
    TODO   no hand-written query yet.

Writes results/conformance.csv (one row per suite, case, mode, engine) and
keeps every intermediate file under results/raw/conformance/ (not versioned).
"""

import argparse
import concurrent.futures as cf
import csv
import os
import re
import shutil
import sys

from harness import ENGINES, HAND, RESULTS, RML2SG, SUITES, VERSIONS, java
from harness import rdfcompare, sandbox, sg

SG_ENGINES = ("sg-java", "sg-java-2.1.0", "pysparql-generate")
RML_ENGINES = ("rpt",)
MODES = {"hand": SG_ENGINES, "translated": SG_ENGINES, "rml": RML_ENGINES}

RAW = os.path.join(RESULTS, "raw", "conformance")
TRANSLATOR = "rml2sparql-generate.rqg"

# Base IRI used to resolve relative IRIs, per suite: the old suite's mappings
# all declare @base <http://example.com/base/>; rml-core gives it in its
# metadata (base_iri column).
DEFAULT_BASE = {"rml-test-cases": "http://example.com/base/",
                "rml-core": "http://example.com/", "kgc-bench-extra": "http://example.com/"}

# Invalid-mapping cases have no hand-written counterpart: a query is not a
# mapping, so "a TriplesMap without subject map" cannot even be written.
INVALID = {
    "0002c": "undefined reference: the hand-written query would refer to a column that does not exist",
    "0002e": "undefined rr:tableName / rml:path: nothing to write a query for",
    "0002g": "invalid JSONPath: nothing to write a query for",
    "0004b": "literal subject: inexpressible in a GENERATE template",
    "0007h": "non-IRI graph name: inexpressible",
    "0012c": "TriplesMap without subjectMap: impossible by construction",
    "0012d": "TriplesMap with two subjectMaps: impossible by construction",
    "0015b": "invalid language tag in the mapping: a typo in a query literal",
    "0019b": "data error expected",
    "0023a": "invalid IRI template", "0023b": "invalid IRI template",
    "0023c": "invalid IRI template", "0023d": "invalid IRI template",
    "0023e": "invalid IRI template",
    "0024a": "constant term map with an incompatible term type",
    "0025b": "wrong reference into an array",
}


def cases(suite, formats):
    """[(case id, data format, expects error, base IRI, input files)]."""
    d = SUITES[suite]
    out = []
    if suite == "rml-test-cases":
        meta = os.path.join(os.path.dirname(d), "metadata.csv")
        for r in csv.DictReader(open(meta, newline="", encoding="utf-8")):
            if r["data format"] in formats:
                out.append((r["RML id"], r["data format"],
                            r["error expected?"].strip() == "true",
                            DEFAULT_BASE[suite]))
    else:
        meta = os.path.join(d, "metadata.csv")
        for r in csv.DictReader(open(meta, newline="", encoding="utf-8")):
            fmt = r["ID"].rsplit("-", 1)[1]
            if fmt in formats:
                out.append((r["ID"], fmt, r["error"].strip() == "true",
                            r["base_iri"] or DEFAULT_BASE[suite]))
    return out


def prepare_inputs(case_dir, work):
    """Copy the case's input documents (not its mapping nor expected output)."""
    os.makedirs(work, exist_ok=True)
    for f in os.listdir(case_dir):
        if f not in ("mapping.ttl", "output.nq") and \
                os.path.isfile(os.path.join(case_dir, f)):
            shutil.copy(os.path.join(case_dir, f), work)


def install_translator(work, src=None):
    """Copy the translator (entry query, templates/, iterators/) into a
    working directory: its named templates are files resolved against -b.
    src: another copy of the translator (default: the pinned one, RML2SG)."""
    src = src or RML2SG
    shutil.copy(os.path.join(src, TRANSLATOR), work)
    for d in ("templates", "iterators"):
        shutil.copytree(os.path.join(src, d), os.path.join(work, d),
                        dirs_exist_ok=True)


def translate(engine, mapping, work, base):
    """Run rml2sparql-generate on a mapping; return (generated query text or
    None, error)."""
    os.makedirs(os.path.join(work, "dataset"), exist_ok=True)
    shutil.copy(mapping, os.path.join(work, "dataset", "default.ttl"))
    install_translator(work)
    r = sg.run(engine, work, TRANSLATOR, "generated.rqg", base=base, timeout=120)
    if not r["ok"]:
        return None, "translation failed: " + r["error"]
    text = open(r["output"], encoding="utf-8").read()
    if "#ERROR" in text:
        line = [l for l in text.splitlines() if "#ERROR" in l][0]
        return None, "translator reports: " + line.split("#ERROR", 1)[1].strip(" :")
    return text, ""


def run_case(suite, case, fmt, expects_error, base, mode, engine):
    case_dir = os.path.join(SUITES[suite], case)
    work = os.path.join(RAW, engine, mode, suite, case)
    shutil.rmtree(work, ignore_errors=True)
    if mode == "rml":
        return run_rml_engine(engine, case_dir, work, expects_error)
    if mode == "hand":
        if expects_error:
            num = case[5:10]
            return "N/A", INVALID.get(num, "invalid mapping: no query to write")
        q = os.path.join(HAND, suite, case + ".rqg")
        if not os.path.exists(q):
            return "TODO", ""
        prepare_inputs(case_dir, work)
        shutil.copy(q, os.path.join(work, "query.rqg"))
    else:
        # the translator is run by the Java engine when the engine under test
        # cannot run it (pysparql-generate: no nested TEMPLATE)
        tengine = "sg-java" if engine == "pysparql-generate" else engine
        text, err = translate(tengine, os.path.join(case_dir, "mapping.ttl"),
                              os.path.join(work, "translation"), base)
        if text is None:
            return ("PASS", "error raised: " + err) if expects_error else ("FAIL", err)
        prepare_inputs(case_dir, work)
        with open(os.path.join(work, "query.rqg"), "w", encoding="utf-8") as f:
            f.write(text)
    # a case that expects an error: a missing document is one (RML 0002e);
    # the engine's default, a warning, suits the other cases
    r = sg.run(engine, work, "query.rqg", "output.nq", base=base,
               fmt=_format_for(os.path.join(work, "query.rqg")), timeout=120,
               extra=sg.fail_on_missing(engine) if expects_error else ())
    if not r["ok"]:
        if engine == "pysparql-generate" and not expects_error and \
                re.search(r"needs an RDF dataset|not supported|unsupported", r["error"]):
            return "N/A", "engine: " + r["error"]
        return ("PASS", "error raised: " + r["error"]) if expects_error \
            else ("FAIL", r["error"])
    if expects_error:
        return "FAIL", "no error raised"
    try:
        got = rdfcompare.load_dataset(r["output"], "nquads")
    except Exception as e:
        return "FAIL", "output does not parse: %s" % str(e)[:200]
    if mode == "translated":
        # Skolem IRIs back to blank nodes, for a translation that writes
        # Skolem IRIs; rml2sparql-generate now writes fun:bnode blank nodes
        got = rdfcompare.deskolemize(got)
    expected = rdfcompare.load_dataset(os.path.join(case_dir, "output.nq"), "nquads")
    ok, detail = rdfcompare.datasets_isomorphic(got, expected)
    if not ok and mode == "translated" and \
            any(n is not None for n in rdfcompare.graphs_by_name(expected)) and \
            rdfcompare.default_graphs_isomorphic(got, expected):
        return "N/A", ("graph maps: GENERATE templates hold triples, not quads "
                       "(GRAPH planned for 2.3); the default graph is isomorphic")
    return ("PASS" if ok else "FAIL"), detail


_RML_ERROR = re.compile(r"(^|\s|\[)(ERROR|FATAL)(\]|\s)|Exception in thread|^Caused by:", re.M)


def run_rml_engine(engine, case_dir, work, expects_error):
    """An RML engine on the case's mapping, run in the directory of its sources."""
    prepare_inputs(case_dir, work)
    shutil.copy(os.path.join(case_dir, "mapping.ttl"), work)
    if engine != "rpt":
        raise ValueError("unknown RML engine %s" % engine)
    jar = os.path.join(ENGINES, "rpt-%s.jar" % VERSIONS["RPT_VERSION"])
    steps = [([java(), "-jar", jar, "rmltk", "rml", "to", "sparql", "mapping.ttl"], "queries.rq"),
             ([java(), "-jar", jar, "integrate", "queries.rq", "--out-format", "nq"], "output.nq")]
    for cmd, out in steps:
        with open(os.path.join(work, out), "w", encoding="utf-8") as f:
            r = sandbox.run(cmd, 120, cwd=work, stdout=f)
        m = _RML_ERROR.search(r["stderr"])
        if r["status"] != "ok" or m:
            line = (r["stderr"][m.start():].strip().splitlines() or [""])[0] if m \
                else "%s: %s" % (r["status"], r["stderr"].strip()[-200:])
            line = sg._clean(line)
            return ("PASS", "error raised: " + line) if expects_error else ("FAIL", line)
    if expects_error:
        return "FAIL", "no error raised"
    try:
        got = rdfcompare.load_dataset(os.path.join(work, "output.nq"), "nquads")
    except Exception as e:
        return "FAIL", "output does not parse: %s" % str(e)[:200]
    expected = rdfcompare.load_dataset(os.path.join(case_dir, "output.nq"), "nquads")
    ok, detail = rdfcompare.datasets_isomorphic(got, expected)
    return ("PASS" if ok else "FAIL"), detail


def engine_version(engine):
    if engine.startswith("sg-java"):
        return sg.jar_label(engine)
    if engine == "pysparql-generate":
        from harness.engines import pysg_version
        return pysg_version()
    if engine == "rpt":
        return "RPT " + VERSIONS.get("RPT_VERSION", "")
    return ""


def _format_for(query_path):
    """GENERATE queries are asked for N-Triples; TEMPLATE queries write their
    own text (here, N-Quads) and refuse an output format."""
    text = open(query_path, encoding="utf-8").read()
    for line in text.splitlines():
        s = line.strip().upper()
        if s.startswith("GENERATE"):
            return "NT"
        if s.startswith("TEMPLATE"):
            return None
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--suites", nargs="*", default=[s for s in SUITES if s != "kgc-bench-extra"],
                    help="default: the official suites; also kgc-bench-extra")
    ap.add_argument("--modes", nargs="*", default=list(MODES))
    ap.add_argument("--engines", nargs="*", default=["sg-java", "sg-java-2.1.0"])
    ap.add_argument("--mem-cap", help="memory cap of every engine process: default "
                    "KGC_BENCH_MEM_CAP, else %s; also the cap of all of them together "
                    "(KGC_BENCH_MEM_TOTAL)" % sandbox.DEFAULT_CAP)
    ap.add_argument("--formats", nargs="*", default=["CSV", "JSON", "XML"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=2,
                    help="cases run at once (default 2: at most two JVMs at a time)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-write", action="store_true",
                    help="do not update results/conformance.csv")
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    if sandbox.resolve():
        sandbox.setup(sandbox.resolve())
    versions = {e: engine_version(e) for e in args.engines}

    todo = []
    for suite in args.suites:
        for case, fmt, err, base in cases(suite, set(args.formats)):
            if args.only and case not in args.only:
                continue
            for mode in args.modes:
                for engine in args.engines:
                    if engine in MODES[mode]:
                        todo.append((suite, case, fmt, err, base, mode, engine))
    rows = []
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        futs = {ex.submit(run_case, *t): t for t in todo}
        for fu in cf.as_completed(futs):
            suite, case, fmt, err, base, mode, engine = futs[fu]
            try:
                status, detail = fu.result()
            except Exception as e:  # a harness bug must not hide the others
                status, detail = "FAIL", "harness: %s: %s" % (type(e).__name__, e)
            rows.append({"suite": suite, "case": case, "format": fmt,
                         "error_expected": err, "mode": mode, "engine": engine,
                         "version": versions[engine],
                         "status": status, "detail": detail.replace("\n", " ")})
            if not args.quiet or status == "FAIL":
                print("%-15s %-16s %-10s %-16s %-4s %s" % (
                    suite, case, mode, engine, status, detail[:110]), flush=True)
    rows.sort(key=lambda r: (r["suite"], r["case"], r["mode"], r["engine"]))
    summary = summarise(rows)
    for line in summary:
        print(line)
    if not args.no_write and not args.only:
        write(rows)
    return 0


def summarise(rows):
    from collections import Counter
    c = Counter((r["suite"], r["format"], r["mode"], r["engine"], r["status"])
                for r in rows)
    keys = sorted({k[:4] for k in c})
    out = ["", "%-15s %-5s %-10s %-16s %5s %5s %5s %5s" % (
        "suite", "fmt", "mode", "engine", "PASS", "FAIL", "N/A", "TODO")]
    for k in keys:
        out.append("%-15s %-5s %-10s %-16s %5d %5d %5d %5d" % (
            k + tuple(c[k + (s,)] for s in ("PASS", "FAIL", "N/A", "TODO"))))
    return out


def write(rows):
    """Merge into results/conformance.csv: rows of other (suite, mode,
    engine) combinations are kept."""
    path = os.path.join(RESULTS, "conformance.csv")
    fields = ["suite", "case", "format", "error_expected", "mode", "engine",
              "version", "status", "detail"]
    keep = []
    done = {(r["suite"], r["mode"], r["engine"]) for r in rows}
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            if (r["suite"], r["mode"], r["engine"]) not in done:
                keep.append(r)
    allrows = sorted(keep + rows, key=lambda r: (r["suite"], r["case"], r["mode"], r["engine"]))
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)
    print("results/conformance.csv written (%d rows)" % len(allrows))


if __name__ == "__main__":
    sys.exit(main())
