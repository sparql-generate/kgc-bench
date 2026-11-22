"""Portability of SPARQL Anything queries (positioning, argument 7): SPARQL
Anything queries parse as SPARQL 1.1, but what do other SPARQL engines answer?

    python -m harness.portability [--mem-cap 8G]

The queries of positioning/portability/queries/ (over the people files of the
slicing scenario, and the issue #701 reproduction) are run on SPARQL Anything
(the reference) and on plain SPARQL engines, on an empty dataset: Apache Jena
ARQ, rdflib, Oxigraph, Comunica, and SPARQL-Generate. Each outcome is one of:
same (as SPARQL Anything: same multiset of solutions, or isomorphic graph),
different, empty, error (with its first line).

Writes results/portability.csv; intermediate files under results/raw/portability/.
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from collections import Counter

from harness import ENGINES, RESULTS, ROOT, VERSIONS, java, rdfcompare, sandbox
from harness import sg as sgcli
from harness.slicing import solutions

SCEN = os.path.join(ROOT, "positioning", "portability")
RAW = os.path.join(RESULTS, "raw", "portability")
_ERROR = re.compile(r"(^|\s|\[)(ERROR|FATAL)(\]|\s|:)|Exception|Error:|Could not|Traceback", re.M)


def engines():
    jena = os.path.join(ENGINES, "apache-jena-%s" % VERSIONS["JENA_VERSION"], "bin", "arq")
    comunica = os.path.join(ENGINES, "comunica", "node_modules", ".bin", "comunica-sparql")
    sa = os.path.join(ENGINES, "sparql-anything-%s.jar" % VERSIONS["SPARQL_ANYTHING_VERSION"])
    runner = os.path.join(SCEN, "run_python.py")
    jhome = os.path.dirname(os.path.dirname(java()))

    def sa_cmd(q, out, construct):
        return [java(), "-jar", sa, "-q", q, "-f", "NT" if construct else "JSON", "-o", out]

    def jena_cmd(q, out, construct):
        return ["sh", "-c", "JAVA_HOME=%s %s --query %s --results=%s > %s" % (
            jhome, jena, rdfcompare._q(q), "NT" if construct else "JSON", rdfcompare._q(out))]

    def sg_cmd(q, out, construct):
        w = os.path.dirname(q)
        return sgcli.command("sg-java", w, os.path.basename(q), os.path.basename(out),
                             fmt="NT" if construct else "JSON", log="WARN")

    def py_cmd(name):
        return lambda q, out, construct: [sys.executable, runner, name, q, out]

    def comunica_cmd(q, out, construct):
        return ["sh", "-c", "%s -f %s -t %s > %s" % (
            comunica, rdfcompare._q(q),
            "application/n-triples" if construct else "application/sparql-results+json",
            rdfcompare._q(out))]

    import importlib.metadata as md
    return [
        ("sparql-anything", "SPARQL Anything " + VERSIONS["SPARQL_ANYTHING_VERSION"], sa_cmd),
        ("jena-arq", "Apache Jena ARQ " + VERSIONS["JENA_VERSION"], jena_cmd),
        ("rdflib", "rdflib " + md.version("rdflib"), py_cmd("rdflib")),
        ("oxigraph", "pyoxigraph " + md.version("pyoxigraph"), py_cmd("oxigraph")),
        ("comunica", "Comunica (@comunica/query-sparql) " + VERSIONS["COMUNICA_VERSION"],
         comunica_cmd),
        ("sparql-generate", "SPARQL-Generate " + sgcli.jar_label("sg-java"), sg_cmd),
    ]


_MESSAGE = re.compile(r"(?:^|\s)((?:[\w.]+\.)?\w*(?:Exception|Error)\b:?.*)$", re.M)


def message(log):
    """The most telling line of an error log: the last 'XxxError: ...' of a
    Python traceback, the deepest 'Caused by' of a Java one, else the first
    line that reports an error."""
    lines = [l.strip() for l in log.splitlines() if l.strip()]
    caused = [l for l in lines if l.startswith("Caused by:")]
    if caused:
        return caused[-1][len("Caused by:"):].strip()[:200]
    found = [m.group(1).strip() for m in _MESSAGE.finditer(log) if ":" in m.group(1)]
    if found:
        return (found[-1] if "Traceback" in log else found[0])[:200]
    m = _ERROR.search(log)
    return (log[m.start():].strip().splitlines()[0][:200]) if m else ""


def outcome(construct, out, ref):
    """(outcome, number of solutions or triples)."""
    if construct:
        ds = rdfcompare.load_dataset(out, "nquads")
        n = len(list(ds.quads((None, None, None, None))))
        if n == 0:
            return "empty", 0
        if ref is None:
            return "reference", n
        if isinstance(ref, Counter):
            return "different", n
        ok, _ = rdfcompare.datasets_isomorphic(ds, ref)
        return ("same" if ok else "different"), n
    sols = solutions(out)
    n = sum(sols.values())
    if n == 0:
        return "empty", 0
    if ref is None:
        return "reference", n
    return ("same" if _plain(sols) == _plain(ref) else "different"), n


def _plain(sols):
    """Solutions with xsd:string literals as simple literals (RDF 1.1)."""
    out = Counter()
    for k, v in sols.items():
        out[tuple(t if not (t and t[2] == "http://www.w3.org/2001/XMLSchema#string")
                  else (t[0], t[1], None, t[3]) for t in k)] += v
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mem-cap")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--engines", nargs="*",
                    help="engines to run (default: all); the others' rows are kept, and "
                    "SPARQL Anything's answers, if it is not run, are read from its last outputs")
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    data = os.path.join(RAW, "data")
    sys.path.insert(0, os.path.join(ROOT, "positioning", "slicing"))
    import make_data
    make_data.main(data)
    open(os.path.join(data, "v.json"), "w").write('{"a":1}\n')
    rows = []
    qdir = os.path.join(SCEN, "queries")
    engs = engines()
    run = args.engines or [e[0] for e in engs]
    previous = []
    path = os.path.join(RESULTS, "portability.csv")
    if args.engines and os.path.exists(path):
        previous = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8"))
                    if r["engine"] not in run]
    for qf in sorted(os.listdir(qdir)):
        name = qf[:-3]
        text = open(os.path.join(qdir, qf), encoding="utf-8").read().replace("%DATA%", data)
        construct = re.search(r"^\s*CONSTRUCT", text, re.M) is not None
        ref = None
        for eng, version, cmd in engs:
            work = os.path.join(RAW, name, eng)
            if eng not in run:
                if eng == "sparql-anything":
                    # its answer from its last run: the reference of the others
                    out = os.path.join(work, "out." + ("nt" if construct else "json"))
                    ref = (rdfcompare.load_dataset(out, "nquads") if construct else solutions(out)) \
                        if os.path.exists(out) and os.path.getsize(out) else \
                        Counter({("<SPARQL Anything failed>",): 1})
                continue
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(work)
            q = os.path.join(work, "query.rq")
            open(q, "w", encoding="utf-8").write(text)
            out = os.path.join(work, "out." + ("nt" if construct else "json"))
            r = sandbox.run(cmd(q, out, construct), args.timeout, cwd=work)
            log = r["stderr"] + r["stdout"]
            n, detail = "", ""
            if r["status"] != "ok" or not os.path.exists(out) or \
                    (os.path.getsize(out) == 0 and _ERROR.search(log)):
                res = "error"
                detail = message(log) or r["status"]
            else:
                try:
                    res, n = outcome(construct, out, ref)
                except Exception as e:
                    res, detail = "error", "output: %s" % str(e)[:150]
                if _ERROR.search(log) and res in ("empty", "reference", "different"):
                    detail = message(log)
            if eng == "sparql-anything":
                # the reference, even when empty (issue #701) or failed
                if res in ("reference", "empty"):
                    ref = (rdfcompare.load_dataset(out, "nquads") if construct else solutions(out))
                else:
                    ref = Counter({("<SPARQL Anything failed>",): 1})
                res = {"reference": "answer"}.get(res, res)
            detail = detail.replace(data, "%DATA%").replace(RAW, "<raw>").replace("\n", " ")
            rows.append({"query": name, "engine": eng, "version": version, "outcome": res,
                         "results": n, "detail": detail})
            print("%-26s %-16s %-9s %4s %s" % (name, eng, res, n, detail[:90]), flush=True)
    order = {e[0]: i for i, e in enumerate(engs)}
    rows = sorted(previous + rows, key=lambda r: (r["query"], order.get(r["engine"], 99)))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["query", "engine", "version", "outcome", "results",
                                          "detail"])
        w.writeheader()
        w.writerows(rows)
    print("results/portability.csv written (%d rows)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
