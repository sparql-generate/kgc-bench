"""Semantics drift under slicing (positioning, argument 2): does the setting
that makes large inputs fit in memory change the answers?

    python -m harness.slicing [--mem-cap 8G]

SPARQL Anything: the 15 questions of positioning/slicing/queries/sa/ over a CSV
file, a top-level JSON array and an XML file (24 people), with slice=false
(the reference), slice=true, and slice=true with slice.size 2, 10 and 1000.
SPARQL-Generate: the counterparts of 10 of them over CSV (iter:CSV) and JSON
(iter:JSONSurfer), with the iterator in one batch (the reference) and in
batches of 1, 2, 10 and 1000. A configuration "changes" a question when its
multiset of solutions differs from the reference's; the warnings printed are
recorded.

Writes results/slicing.csv; intermediate files under results/raw/slicing/.
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from collections import Counter

from harness import ENGINES, RESULTS, ROOT, VERSIONS, java, sandbox
from harness import sg as sgcli

SCEN = os.path.join(ROOT, "positioning", "slicing")
RAW = os.path.join(RESULTS, "raw", "slicing")
SA_CONFIGS = [("slice=false", ""), ("slice=true", ",slice=true"),
              ("slice.size=2", ",slice=true,slice.size=2"),
              ("slice.size=10", ",slice=true,slice.size=10"),
              ("slice.size=1000", ",slice=true,slice.size=1000")]
SG_CONFIGS = [("one batch", ""), ("batch=1", ", 1"), ("batch=2", ", 2"),
              ("batch=10", ", 10"), ("batch=1000", ", 1000")]
_WARN = re.compile(r"\bWARN(ING)?\b")
_ERROR = re.compile(r"(^|\s|\[)ERROR(\]|\s)|Exception in thread", re.M)


def solutions(path):
    """The multiset of solutions of a SPARQL JSON results file."""
    with open(path, encoding="utf-8") as f:
        res = json.load(f)
    vars_ = res["head"]["vars"]
    out = Counter()
    for b in res["results"]["bindings"]:
        out[tuple(_term(b.get(v)) for v in vars_)] += 1
    return out


def _term(t):
    if t is None:
        return None
    return (t["type"].replace("typed-literal", "literal"), t["value"],
            t.get("datatype"), t.get("xml:lang"))


def run_sa(query, data, opts, work, timeout):
    os.makedirs(work, exist_ok=True)
    text = open(query, encoding="utf-8").read().replace("%DATA%", data).replace("%OPTIONS%", opts)
    q = os.path.join(work, "query.rq")
    open(q, "w", encoding="utf-8").write(text)
    out = os.path.join(work, "out.json")
    jar = os.path.join(ENGINES, "sparql-anything-%s.jar" % VERSIONS["SPARQL_ANYTHING_VERSION"])
    r = sandbox.run([java(), "-jar", jar, "-q", q, "-f", "JSON", "-o", out], timeout, cwd=work)
    return r, out


def run_sg(query, data, batch, work, timeout):
    os.makedirs(work, exist_ok=True)
    for f in os.listdir(data):
        if not os.path.exists(os.path.join(work, f)):
            os.symlink(os.path.join(data, f), os.path.join(work, f))
    text = open(query, encoding="utf-8").read().replace("%BATCH%", batch)
    open(os.path.join(work, "query.rqg"), "w", encoding="utf-8").write(text)
    cmd = sgcli.command("sg-java", work, "query.rqg", "out.json", base="http://example.org/",
                        fmt="JSON", log="WARN")
    r = sandbox.run(cmd, timeout, cwd=work)
    return r, os.path.join(work, "out.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mem-cap", help="memory cap of every engine process (default "
                    "KGC_BENCH_MEM_CAP, else %s)" % sandbox.DEFAULT_CAP)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--engines", nargs="*", default=["sparql-anything", "sg-java"],
                    help="the rows of the engines not run are kept")
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    for e in args.engines:
        shutil.rmtree(os.path.join(RAW, {"sparql-anything": "sa", "sg-java": "sg"}[e]),
                      ignore_errors=True)
    data = os.path.join(RAW, "data")
    sys.path.insert(0, SCEN)
    import make_data
    make_data.main(data)
    rows = []

    def record(engine, version, fmt, name, config, r, out, ref):
        status, n, same = r["status"], "", ""
        sols = None
        if status == "ok" and (not os.path.exists(out) or _ERROR.search(r["stderr"])):
            status = "error"
        if status == "ok":
            try:
                sols = solutions(out)
                n = sum(sols.values())
            except Exception as e:
                status = "error: %s" % str(e)[:80]
        if ref is not None and sols is not None:
            same = "yes" if sols == ref else "no"
        warns = [l.strip() for l in r["stderr"].splitlines() if _WARN.search(l)]
        rows.append({"engine": engine, "version": version, "format": fmt, "query": name,
                     "config": config, "status": status, "solutions": n, "same": same,
                     "warnings": " | ".join(w[-160:] for w in warns[:3])})
        print("%-16s %-5s %-20s %-16s %-6s %4s %-3s %s" % (
            engine, fmt, name, config, status[:6], n, same, rows[-1]["warnings"][:80]), flush=True)
        return sols

    sa_version = "SPARQL Anything " + VERSIONS["SPARQL_ANYTHING_VERSION"]
    for fmt in (("csv", "json", "xml") if "sparql-anything" in args.engines else ()):
        qdir = os.path.join(SCEN, "queries", "sa", fmt)
        for qf in sorted(os.listdir(qdir)):
            name = qf[:-3]
            ref = None
            for config, opts in SA_CONFIGS:
                work = os.path.join(RAW, "sa", fmt, name, config)
                r, out = run_sa(os.path.join(qdir, qf), data, opts, work, args.timeout)
                sols = record("sparql-anything", sa_version, fmt, name, config, r, out, ref)
                if ref is None:
                    ref = sols if sols is not None else Counter({("<reference failed>",): 1})
    sg_version = "SPARQL-Generate " + sgcli.jar_label("sg-java")
    for fmt in (("csv", "json") if "sg-java" in args.engines else ()):
        qdir = os.path.join(SCEN, "queries", "sg", fmt)
        for qf in sorted(os.listdir(qdir)):
            name = qf[:-4]
            ref = None
            for config, batch in SG_CONFIGS:
                work = os.path.join(RAW, "sg", fmt, name, config.replace(" ", "-"))
                r, out = run_sg(os.path.join(qdir, qf), data, batch, work, args.timeout)
                sols = record("sg-java", sg_version, fmt, name, config, r, out, ref)
                if ref is None:
                    ref = sols if sols is not None else Counter({("<reference failed>",): 1})
    path = os.path.join(RESULTS, "slicing.csv")
    if os.path.exists(path):
        rows = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8"))
                if r["engine"] not in args.engines] + rows
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["engine", "version", "format", "query", "config",
                                          "status", "solutions", "same", "warnings"])
        w.writeheader()
        w.writerows(rows)
    print(summary(rows))
    print("results/slicing.csv written (%d rows)" % len(rows))
    return 0


def summary(rows):
    out = ["", "%-16s %-5s %-16s %s" % ("engine", "fmt", "config", "questions whose answers change")]
    keys = []
    for r in rows:
        k = (r["engine"], r["format"], r["config"])
        if k not in keys:
            keys.append(k)
    for k in keys:
        rs = [r for r in rows if (r["engine"], r["format"], r["config"]) == k]
        if not any(r["same"] for r in rs):
            continue
        changed = [r["query"][:3] for r in rs if r["same"] == "no"]
        warned = sum(1 for r in rs if r["warnings"])
        out.append("%-16s %-5s %-16s %d/%d %s%s" % (k + (len(changed), len(rs), " ".join(changed),
                                                         "  (%d with warnings)" % warned if warned else "")))
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
