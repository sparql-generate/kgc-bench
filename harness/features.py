"""The feature matrix (positioning, argument 8): minimal executable cases,
each with its expected output, run on SPARQL-Generate and SPARQL Anything.

    python -m harness.features [--engines sg-java sparql-anything] [--mem-cap 16G]

The cases are in positioning/features/cases.py. Outcomes: pass (the expected
output: graph isomorphism, or the same text), fail (with the difference),
error, not expressible (the engine has no construct for it: the reason), not
run (the case needs a service this machine does not have). One engine process
at a time, under the limits of harness.perf; a local HTTP server answers the
case that needs one.

Writes results/features.csv (rows of engines not run this time are kept);
intermediate files under results/raw/features/.
"""

import argparse
import csv
import http.server
import json
import os
import re
import shutil
import socketserver
import sys
import threading

from harness import ENGINES, RESULTS, ROOT, VERSIONS, java, rdfcompare, sandbox
from harness import sg as sgcli

SCEN = os.path.join(ROOT, "positioning", "features")
RAW = os.path.join(RESULTS, "raw", "features")
_ERROR = re.compile(r"(^|\s|\[)(ERROR|FATAL)(\]|\s)|Exception in thread|^Caused by:", re.M)
ENGINE_NAMES = ("sg-java", "sparql-anything")


class _Items(http.server.BaseHTTPRequestHandler):
    """GET /item/<n>: {"label": ...} with the header X-Version: 7. In HTTP/1.1:
    fun:HTTPExtractBody and fun:HTTPExtractHeader (SPARQL-Generate 2.2.3)
    require a response that starts with "HTTP/1.1 "."""
    LABELS = {"1": "one", "2": "two"}
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        n = self.path.rstrip("/").rsplit("/", 1)[-1]
        if n not in self.LABELS:
            self.send_error(404)
            return
        body = json.dumps({"label": self.LABELS[n]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Version", "7")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def server():
    # threads: an HTTP/1.1 client may keep a connection open while it opens another
    socketserver.ThreadingTCPServer.daemon_threads = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Items)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def write_inputs(case, work, port):
    os.makedirs(work, exist_ok=True)
    for name, content in case.get("files", {}).items():
        data = content() if callable(content) else content
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(os.path.join(work, name), mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as f:
            f.write(data)


def run_engine(engine, case, work, port, timeout):
    """(status, output path, log)."""
    kind = case["kind"]
    if engine == "sg-java":
        text = case["sg"].replace("%PORT%", str(port))
        open(os.path.join(work, "query.rqg"), "w", encoding="utf-8").write(text)
        for name, t in case.get("sg_files", {}).items():
            open(os.path.join(work, name), "w", encoding="utf-8").write(t.replace("%PORT%", str(port)))
        template = re.search(r"^\s*TEMPLATE", text, re.M) is not None
        out = "out.txt" if template else "out.nt"
        cmd = sgcli.command("sg-java", work, "query.rqg", out, base="http://example.org/",
                            fmt=None if template else "NT", log="WARN")
    else:
        text = case["sa"].replace("%DATA%", work).replace("%PORT%", str(port))
        q = os.path.join(work, "query.rq")
        open(q, "w", encoding="utf-8").write(text)
        fmt, out = {"graph": ("NT", "out.nt"), "quads": ("NQ", "out.nq"),
                    "text": ("JSON", "out.json")}[kind]
        jar = os.path.join(ENGINES, "sparql-anything-%s.jar" % VERSIONS["SPARQL_ANYTHING_VERSION"])
        cmd = [java(), "-jar", jar, "-q", q, "-f", fmt, "-o", os.path.join(work, out)]
    r = sandbox.run(cmd, timeout, cwd=work)
    log = r["stderr"] + r["stdout"]
    status = r["status"]
    if status == "ok" and _ERROR.search(log):
        status = "error"
    return status, os.path.join(work, out), log


def judge(case, out):
    """(pass/fail, detail)."""
    kind = case["kind"]
    if kind == "text":
        if out.endswith(".json"):
            res = json.load(open(out, encoding="utf-8"))["results"]["bindings"]
            got = next(iter(res[0].values()))["value"] if res and res[0] else ""
        else:
            got = open(out, encoding="utf-8").read()
        ok = got.strip() == case["expected"].strip()
        return ("pass", "") if ok else ("fail", "got %r" % got[:150])
    exp = os.path.join(os.path.dirname(out), "expected.nq")
    open(exp, "w", encoding="utf-8").write(case["expected"])
    got = rdfcompare.load_dataset(out, "nquads")
    ok, detail = rdfcompare.datasets_isomorphic(got, rdfcompare.load_dataset(exp, "nquads"))
    return ("pass", "") if ok else ("fail", detail)


def _message(log):
    lines = [l.strip() for l in log.splitlines() if l.strip()]
    caused = [l for l in lines if l.startswith("Caused by:")]
    if caused:
        return caused[-1][len("Caused by:"):].strip()
    m = _ERROR.search(log)
    return (log[m.start():].strip().splitlines() or [""])[0] if m else (lines[-1] if lines else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engines", nargs="*", default=list(ENGINE_NAMES))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--mem-cap")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    sys.path.insert(0, SCEN)
    import cases as C
    srv = server()
    port = srv.server_address[1]
    versions = {"sg-java": "SPARQL-Generate " + sgcli.jar_label("sg-java"),
                "sparql-anything": "SPARQL Anything " + VERSIONS["SPARQL_ANYTHING_VERSION"]}
    rows = []
    for case in C.CASES:
        if args.only and case["name"] not in args.only:
            continue
        for eng in args.engines:
            key = "sg" if eng == "sg-java" else "sa"
            note = case.get(key + "_note", "")
            row = {"case": case["name"], "what": case["what"], "engine": eng,
                   "version": versions[eng], "outcome": "", "detail": "", "note": note}
            if case.get(key + "_na"):
                row.update(outcome="not expressible", detail=case[key + "_na"])
            elif case.get("not_run"):
                row.update(outcome="not run", detail=case["not_run"])
            else:
                work = os.path.join(RAW, case["name"], eng)
                shutil.rmtree(work, ignore_errors=True)
                write_inputs(case, work, port)
                status, out, log = run_engine(eng, case, work, port, args.timeout)
                if status != "ok" or not os.path.exists(out):
                    row.update(outcome="error", detail=(_message(log) or status)[:200])
                else:
                    try:
                        row["outcome"], row["detail"] = judge(case, out)
                    except Exception as e:
                        row.update(outcome="fail", detail="output: %s" % str(e)[:150])
                    warn = [l.strip() for l in log.splitlines() if "WARN" in l
                            and "Open iterator" not in l and "No query pattern" not in l]
                    if row["outcome"] == "fail" and warn:
                        row["detail"] = (warn[0][-150:] + "; " + row["detail"])
                row["detail"] = row["detail"].replace(RAW, "<raw>").replace("\n", " ")[:300]
            rows.append(row)
            print("%-18s %-16s %-15s %s" % (case["name"], eng, row["outcome"], row["detail"][:100]),
                  flush=True)
    srv.shutdown()
    path = os.path.join(RESULTS, "features.csv")
    keep = []
    if os.path.exists(path):
        done = {(r["case"], r["engine"]) for r in rows}
        keep = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8"))
                if (r["case"], r["engine"]) not in done]
    order = {c["name"]: i for i, c in enumerate(C.CASES)}
    allrows = sorted(keep + rows, key=lambda r: (order.get(r["case"], 99), r["engine"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case", "what", "engine", "version", "outcome",
                                          "detail", "note"])
        w.writeheader()
        w.writerows(allrows)
    print("results/features.csv written (%d rows)" % len(allrows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
