"""RQ3 — performance: wall time and peak memory of SPARQL-Generate (Java,
hand-written and translated queries; Python), RML engines and SPARQL
Anything, on the same workloads, with the outputs checked.

    python -m harness.perf [--workloads gtfs nested-json nested-xml flat-csv]
                           [--engines all | sg-java morph-kgc ...]
                           [--scales 1 10] [--runs 3] [--timeout 600] [--mem-cap 16G]
                           [--xmx 12g] [--campaign ID]

Every engine runs as a cold process under /usr/bin/time -v (start-up
included, as a user runs it), in a transient systemd scope (harness.sandbox).
Every run has the same two limits, whatever the engine: memory (--mem-cap,
16G) and time (--timeout, 600 s). A run over a limit is stopped and the
solution is *not viable* at that size: recorded OOM or DNF, never replayed,
and not tried at larger scales. Java engines get a heap of 75% of the memory
limit (--xmx), so that they collect before the limit kills them. The best of --runs is kept, with the
peak resident memory of that run. Outputs: the number of distinct triples is
recorded for every run; at the smallest scale of a workload, every output is
compared with the reference output (Morph-KGC, else SPARQL-Generate) by set
equality of triples, or by isomorphism when blank nodes occur. Outputs of
the larger scales are deleted once counted (--keep-outputs keeps them).

Writes results/perf.csv (one row per workload, scale, engine, written as
soon as measured; rows of other combinations are kept), results/perf-runs.csv
(every run, with the load average when it started) and results/machine.json.
With --campaign ID, the rows are tagged ID and a (workload, scale, engine)
already measured in campaign ID is not run again, whatever its status: an
interrupted campaign is resumed by running the same command, and a failed
case (DNF, OOM, error, or "interrupted" when the harness itself was stopped
during the run) is never replayed automatically. When the reference engine
is not run, the triple counts are compared with the reference's count kept in
perf.csv (a count does not depend on the machine). An output that is not
the reference's (another number of distinct triples, or another set at the
smallest scale) is recorded wrong-output, whatever the exit code: it is not
a measurement. Timings taken while other
jobs load the machine are provisional: machine.json records the load before
and after.
"""

import argparse
import csv
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

from harness import RESULTS, VERSIONS, java, rdfcompare, sandbox
from harness import engines as E
from harness import workloads as W

TMP = os.path.join(RESULTS, "tmp", "perf")
# outputs up to this many triples are compared in memory (rdflib); above,
# by their number of distinct triples only
CHECK_LIMIT = 600000
DEFAULT_SCALES = {"gtfs": [1, 10, 100], "nested-json": [10, 100], "nested-xml": [10, 100],
                  "flat-csv": [100, 1000]}
DEFAULT_SCALES.update({w: [1] for w in W.ALL if w.startswith("kgcw-")})
ENGINE_ORDER = ["sg-java", "sg-java-nostream", "sg-java-translated", "sg-java-translated-tau",
                "pysparql-generate", "pysparql-generate-translated", "pysparql-generate-translated-tau",
                "morph-kgc", "rmlmapper", "sdm-rdfizer", "rpt", "sparql-anything"]
# (workload, engine) pairs not run, with the reason
SKIP = {}


def timed(cmd, timeout, cwd=None, env=None):
    """(status, wall_s, peak_rss_mb, stderr tail, sandbox result) of one cold
    process, in a memory-capped scope. Status: ok, error, timeout, oom (killed
    at the cap of the scope), out-of-memory (the engine reports it: Java heap
    exhausted, MemoryError)."""
    r = sandbox.run(cmd, timeout, cwd=cwd, env=env)
    err = r["stderr"]
    status = r["status"]
    if status == "ok" and re.search(r"(^|\s)(ERROR|FATAL)\s|Exception in thread|OutOfMemoryError", err):
        status = "error"
    if status == "error" and re.search(r"OutOfMemoryError|MemoryError|Cannot allocate memory|"
                                       r"Out of Memory Error", err):
        status = "out-of-memory"
    return status, r["wall_s"], r["rss_mb"], err[-600:], r


def machine_info():
    def sh(c):
        try:
            return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
        except Exception:
            return ""
    lscpu = sh("LC_ALL=C lscpu")
    model = re.search(r"Model name:\s*(.*)", lscpu)
    return {
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(),
        "cpu": model.group(1) if model else "",
        "cpus": os.cpu_count(),
        "ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1),
        "kernel": platform.release(),
        "os": sh(". /etc/os-release && echo $PRETTY_NAME"),
        "java": sh("%s -version 2>&1 | head -1" % java()),
        "python": sys.version.split()[0],
        "loadavg": open("/proc/loadavg").read().split()[:3],
        "mem_available_gb": _mem_available_gb(),
        "mem_cap": sandbox.resolve() or "none",
        "busy": busy_processes(),
    }


def _mem_available_gb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return round(int(line.split()[1]) / 2**20, 1)
    return None


def busy_processes(cpu=20.0, rss_gb=1.0):
    """Other processes that load the machine (CPU %% over one second, or
    resident memory): the load the measurements shared the machine with."""
    try:
        import psutil
    except ImportError:
        return []
    me = os.getpid()
    procs = list(psutil.process_iter(["pid", "name", "memory_info", "cmdline"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(1)
    out = []
    for p in procs:
        try:
            c = p.cpu_percent(None)
            m = p.info["memory_info"].rss / 2**30 if p.info["memory_info"] else 0
            if p.pid != me and (c >= cpu or m >= rss_gb):
                out.append({"pid": p.pid, "name": p.info["name"], "cpu": round(c),
                            "rss_gb": round(m, 1),
                            "cmd": " ".join(p.info["cmdline"] or [])[:80]})
        except Exception:
            pass
    return sorted(out, key=lambda x: -x["cpu"])[:15]


_REF = {}


def compare(out_a, fmt_a, out_b, fmt_b, deskolem_a=False):
    """Set equality of triples (isomorphism if blank nodes); (bool, detail).
    The reference (out_b) is parsed once and kept for the other engines."""
    def load(p, f, desk):
        ds = rdfcompare.load_dataset(p, "turtle" if f == "turtle" else "nquads")
        return rdfcompare.deskolemize(ds) if desk else ds
    if out_b not in _REF:
        _REF.clear()
        _REF[out_b] = load(out_b, fmt_b, False)
    return rdfcompare.datasets_isomorphic(load(out_a, fmt_a, deskolem_a), _REF[out_b])


def _lines(path):
    """Lines of an output file that hold a triple (not @prefix / @base)."""
    if not os.path.exists(path):
        return 0
    r = subprocess.run("grep -vc '^@\\|^[[:space:]]*$' %s" % rdfcompare._q(path), shell=True,
                       capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def run_one(workload, scale, engine, args, log):
    work_root = os.path.join(TMP, workload.name, str(scale))
    job = workload.job(scale, work_root)
    ework = os.path.join(work_root, engine.name)
    shutil.rmtree(ework, ignore_errors=True)
    os.makedirs(ework)
    row = {"workload": workload.name, "scale": scale, "engine": engine.name,
           "version": engine.version(), "runs": 0, "status": "", "wall_s": "",
           "wall_median_s": "", "rss_mb": "", "triples": "", "equivalent": "",
           "note": "", "mem_cap": sandbox.resolve() or "none", "campaign": args.campaign or ""}
    try:
        engine.prepare(job, ework, args.xmx)
    except Exception as e:
        row.update(status="error", note=("prepare: %s" % e)[:300])
        return row, None
    if job.get("translation_s", {}).get(engine.name) is not None:
        row["note"] = "translation %.2fs (untimed)" % job["translation_s"][engine.name]
    runs = []
    row_counts = {}
    for k in range(args.runs):
        out = engine.output(ework)
        if os.path.exists(out):
            os.remove(out)
        load1 = open("/proc/loadavg").read().split()[0]
        status, wall, rss, err, res = timed(engine.command(job, ework, args.xmx), args.timeout,
                                            cwd=ework)
        lines = _lines(out) if status == "ok" else None
        runs.append({"workload": workload.name, "scale": scale, "engine": engine.name,
                     "run": k + 1, "status": status, "wall_s": wall, "rss_mb": rss,
                     "lines": lines, "cg_peak_mb": res["cg_peak_mb"],
                     "mem_cap": res["mem_cap"], "load1": load1,
                     "campaign": args.campaign or ""})
        if status == "ok" and "triples" not in row_counts:
            # distinct triples, counted on the first good output (a later run
            # may be interrupted and leave no output)
            row_counts["triples"] = E.count_triples(out, engine.out_format)
            row_counts["lines"] = lines
        log.writerow(runs[-1])
        print("    run %d: %s %.2fs %s MB" % (k + 1, status, wall, rss), flush=True)
        if status == "oom":
            row["note"] = (row["note"] + " killed at the memory cap (%s)" % res["mem_cap"]).strip()
            break
        if status != "ok":
            row["note"] = (row["note"] + " " + err.strip().splitlines()[-1][:200]).strip() if err.strip() else row["note"]
            break
    ok = [r for r in runs if r["status"] == "ok"]
    # an engine that writes a truncated or empty output with exit status 0
    # (SPARQL-Generate 2.2.0, intermittently): such a run is not a timing
    if ok:
        most = max(r["lines"] or 0 for r in ok)
        short = [r for r in ok if (r["lines"] or 0) < most]
        if short:
            row["note"] = (row["note"] + " unstable output: %s lines over the runs" % "/".join(
                str(r["lines"]) for r in ok)).strip()
            for r in short:
                r["status"] = "short-output"
            ok = [r for r in ok if r["status"] == "ok"]
    row["runs"] = len(runs)
    if not ok:
        row["status"] = {"timeout": "DNF", "out-of-memory": "OOM", "oom": "OOM"}.get(
            runs[-1]["status"], "error")
        return row, None
    best = min(ok, key=lambda r: r["wall_s"])
    walls = sorted(r["wall_s"] for r in ok)
    row.update(status="ok", wall_s=best["wall_s"], rss_mb=best["rss_mb"],
               wall_median_s=walls[len(walls) // 2])
    row["triples"] = row_counts.get("triples")
    # the output kept for the check is the last good one
    return row, (engine.output(ework) if runs[-1]["status"] == "ok" else None)


LIMIT_TIME_S = 600


def default_xmx():
    """75% of the memory limit, in megabytes, for the Java heap."""
    cap = sandbox.resolve()
    if not cap:
        return "16g"
    return "%dm" % (sandbox.to_bytes(cap) * 3 // 4 // 2**20)


def viability(row, mem_cap=None, time_s=None):
    """'' (viable), 'memory' or 'time': whether a row stays within the limits
    of a run (the row's own memory cap, else mem_cap; time_s). A run that
    finished over a limit is not viable either (rows measured before the
    limits were set)."""
    st = row.get("status", "")
    cap = row.get("mem_cap") or mem_cap or sandbox.DEFAULT_CAP
    if cap in ("", "none"):
        cap = sandbox.DEFAULT_CAP
    if st == "OOM":
        return "memory"
    if st == "DNF":
        return "memory" if "OOM at a smaller" in (row.get("note") or "") else "time"
    if st != "ok":
        return ""
    limit_mb = sandbox.to_bytes(min(cap, mem_cap or cap, key=sandbox.to_bytes)) / 2**20
    if row.get("rss_mb") and float(row["rss_mb"]) > limit_mb:
        return "memory"
    if row.get("wall_s") and float(row["wall_s"]) > (time_s or LIMIT_TIME_S):
        return "time"
    return ""


def add_cap_option(ap):
    ap.add_argument("--mem-cap", help="memory limit of one run (systemd scope): default "
                    "KGC_BENCH_MEM_CAP, else %s; over it, not viable" % sandbox.DEFAULT_CAP)


def apply_cap_option(args):
    """--mem-cap, for this process and the processes it starts."""
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    cap = sandbox.resolve()
    if cap:
        sandbox.setup(cap)
    print("memory cap: %s per process, %s for slice %s" % (
        cap or "none", sandbox.slice_cap() if cap else "none", sandbox.SLICE), flush=True)
    return cap


RUN_FIELDS = ["date", "campaign", "workload", "scale", "engine", "run", "status", "wall_s",
              "rss_mb", "cg_peak_mb", "mem_cap", "load1"]


def open_runs_log(path):
    """perf-runs.csv in append mode; an older header is migrated first."""
    if os.path.exists(path):
        with open(path, newline="") as f:
            header = next(csv.reader(f), [])
        if header != RUN_FIELDS:
            old = list(csv.DictReader(open(path, newline="")))
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=RUN_FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(old)
    new = not os.path.exists(path)
    rf = open(path, "a", newline="")
    log = csv.DictWriter(rf, fieldnames=RUN_FIELDS, extrasaction="ignore")
    if new:
        log.writeheader()
    return rf, log


def stored_reference(workload, scale):
    """The reference engine's row of perf.csv at (workload, scale), from any
    earlier measurement: its triple count checks the engines run now."""
    path = os.path.join(RESULTS, "perf.csv")
    if not os.path.exists(path):
        return None
    rs = [r for r in csv.DictReader(open(path, newline="")) if r["workload"] == workload
          and float(r["scale"]) == float(scale) and r["status"] == "ok" and r.get("triples")]
    for n in ("morph-kgc", "sg-java"):
        for r in rs:
            if r["engine"] == n:
                return dict(r, engine="%s (stored, %s)" % (n, r.get("date", "")[:10]))
    return None


def measured(campaign):
    """{(workload, scale, engine): row} of perf.csv already measured in the
    campaign (resumption)."""
    path = os.path.join(RESULTS, "perf.csv")
    if not campaign or not os.path.exists(path):
        return {}
    return {(r["workload"], str(r["scale"]), r["engine"]): r
            for r in csv.DictReader(open(path, newline=""))
            if r.get("campaign") == campaign and r.get("status")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workloads", nargs="*",
                    default=[w for w in W.ALL if not w.startswith("kgcw-")],
                    help="default: all but the KGCW tasks; 'all': every workload (%s)" % ", ".join(
                        w for w in W.ALL if w.startswith("kgcw-")))
    ap.add_argument("--engines", nargs="*", default=["all"])
    ap.add_argument("--scales", nargs="*", type=float,
                    help="scales for every workload (default: per workload)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=LIMIT_TIME_S,
                    help="time limit of one run, s (default %d): over it, not viable" % LIMIT_TIME_S)
    ap.add_argument("--xmx", help="Java heap (default: 75%% of the memory limit)")
    add_cap_option(ap)
    ap.add_argument("--campaign", default=os.environ.get("KGC_BENCH_CAMPAIGN"),
                    help="tag the rows; skip what this campaign already measured")
    ap.add_argument("--keep-outputs", action="store_true",
                    help="keep the outputs of the scales above the smallest")
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args(argv)
    apply_cap_option(args)
    args.xmx = args.xmx or default_xmx()
    if "all" in args.workloads:
        args.workloads = list(W.ALL)
    names = ENGINE_ORDER if args.engines in (["all"], []) else args.engines
    engines = [E.BY_NAME[n] for n in names]
    os.makedirs(RESULTS, exist_ok=True)
    info = machine_info()
    info["limits"] = {"memory": sandbox.resolve() or "none", "time_s": args.timeout,
                      "xmx": args.xmx}
    print("machine:", json.dumps(info), flush=True)
    done = measured(args.campaign)
    rows = []
    rf, log = open_runs_log(os.path.join(RESULTS, "perf-runs.csv"))

    class Log:
        def writerow(self, r):
            log.writerow(dict(r, date=info["date"]))
            rf.flush()

    def save():
        write_rows(rows, info["date"])

    for wname in args.workloads:
        wl = W.ALL[wname]
        scales = args.scales or DEFAULT_SCALES[wname]
        scales = [int(s) if float(s).is_integer() else s for s in scales]
        dnf = {}   # engine -> status (DNF, OOM) at a smaller scale: not run again
        for scale in scales:
            if not wl.ensure_data(scale):
                print("%s scale %s: no data (see REPRODUCE.md)" % (wname, scale))
                continue
            print("== %s scale %s" % (wname, scale), flush=True)
            outputs = {}
            job0 = wl.job(scale, os.path.join(TMP, wname, str(scale)))
            for eng in engines:
                if (wname, eng.name) in SKIP:
                    continue
                if eng.lang == "sg" and not job0.get("sg_query") \
                        or eng.lang == "sa" and not job0.get("sa_query"):
                    continue
                if not eng.available():
                    print("  %-20s not available" % eng.name)
                    continue
                prev = done.get((wname, str(scale), eng.name))
                if prev:
                    # measured earlier in this campaign: kept, not re-run
                    rows.append(dict(prev, scale=scale))
                    if prev["status"] in ("DNF", "OOM"):
                        dnf[eng.name] = prev["status"]
                    out = eng.output(os.path.join(TMP, wname, str(scale), eng.name))
                    if prev["status"] == "ok" and os.path.exists(out):
                        outputs[eng.name] = (out, eng.out_format, "-translated" in eng.name)
                    print("  %-20s already measured in campaign %s: %s" % (
                        eng.name, args.campaign, prev["status"]), flush=True)
                    continue
                if eng.name not in dnf:
                    # failed at a smaller scale in an earlier command of the campaign
                    failed = sorted((float(k[1]), r["status"]) for k, r in done.items()
                                    if k[0] == wname and k[2] == eng.name
                                    and float(k[1]) < float(scale) and r["status"] in ("DNF", "OOM"))
                    if failed:
                        dnf[eng.name] = failed[0][1]
                if eng.name in dnf:
                    rows.append({"workload": wname, "scale": scale, "engine": eng.name,
                                 "version": eng.version(), "status": dnf[eng.name],
                                 "mem_cap": sandbox.resolve() or "none",
                                 "campaign": args.campaign or "",
                                 "note": "not run: %s at a smaller scale" % dnf[eng.name]})
                    save()
                    continue
                print("  %s" % eng.name, flush=True)
                # a placeholder, replaced by the result: if the harness is
                # stopped during the run, the case stays "interrupted" and a
                # resumed campaign does not replay it
                rows.append({"workload": wname, "scale": scale, "engine": eng.name,
                             "version": eng.version(), "status": "interrupted",
                             "mem_cap": sandbox.resolve() or "none",
                             "campaign": args.campaign or "",
                             "note": "the harness stopped during this run"})
                save()
                rows.pop()
                row, out = run_one(wl, scale, eng, args, Log())
                rows.append(row)
                if row["status"] in ("DNF", "OOM"):
                    dnf[eng.name] = row["status"]
                if out:
                    if scale == scales[0] or args.keep_outputs or args.no_check:
                        outputs[eng.name] = (out, eng.out_format, "-translated" in eng.name)
                    if scale != scales[0] and not args.keep_outputs:
                        os.remove(out)   # counted; too large to keep at every scale
                print("  %-20s %-5s best %ss  peak %s MB  %s triples  %s" % (
                    eng.name, row["status"], row["wall_s"], row["rss_mb"],
                    row["triples"], row["note"]), flush=True)
                save()
            # triple counts compared with the reference at every scale
            srows = [x for x in rows if x["workload"] == wname and x["scale"] == scale
                     and x.get("status") == "ok"]
            refrow = next((x for n in ("morph-kgc", "sg-java") for x in srows
                           if x["engine"] == n), None) or stored_reference(wname, scale)
            for x in srows:
                if refrow and x is not refrow and str(x.get("triples")) != str(refrow.get("triples")):
                    # not the reference's triples, whatever the exit code (an engine
                    # may write a partial output and exit 0): not a measurement
                    x["equivalent"] = "no"
                    x["status"] = "wrong-output"
                    note = " %s triples, %s for %s" % (x.get("triples"), refrow.get("triples"),
                                                       refrow["engine"])
                    if note.strip() not in (x.get("note") or ""):
                        x["note"] = ((x.get("note") or "") + note).strip()
                elif refrow and x is not refrow and (scale != scales[0] or
                                                     "stored" in refrow["engine"]):
                    x["equivalent"] = "count"
            # outputs checked at the smallest scale, against a reference
            stored = refrow is not None and "stored" in refrow["engine"]
            if not args.no_check and scale == scales[0] and outputs and not stored:
                ref = next((n for n in ("morph-kgc", "sg-java")
                            if n in outputs), next(iter(outputs)))
                for name, (out, fmt, desk) in outputs.items():
                    r = next(x for x in rows if x["workload"] == wname and
                             x["scale"] == scale and x["engine"] == name)
                    if name == ref:
                        r["equivalent"] = "reference"
                        continue
                    if r.get("equivalent") in ("yes", "no"):
                        continue   # checked before the campaign was resumed
                    if int(r.get("triples") or 0) > CHECK_LIMIT:
                        # too large for an in-memory comparison: counts only
                        r["equivalent"] = r.get("equivalent") or "count"
                        continue
                    try:
                        ok, detail = compare(out, fmt, outputs[ref][0], outputs[ref][1], desk)
                    except Exception as e:
                        ok, detail = False, "compare failed: %s" % e
                    r["equivalent"] = "yes" if ok else "no"
                    if not ok:
                        r["status"] = "wrong-output"
                        r["note"] = ((r.get("note") or "") + " vs %s: %s" % (ref, detail))[:400].strip()
                    print("  check %-20s vs %s: %s %s" % (name, ref, r["equivalent"], detail[:150]))
            save()
    rf.close()
    info["loadavg_after"] = open("/proc/loadavg").read().split()[:3]
    info["mem_available_gb_after"] = _mem_available_gb()
    info["campaign"] = args.campaign or ""
    write_machine(info)
    return 0


FIELDS = ["workload", "scale", "engine", "version", "status", "viable", "runs", "wall_s",
          "wall_median_s", "rss_mb", "mem_cap", "triples", "equivalent", "note", "date",
          "campaign"]


def write_rows(rows, date):
    """Merge the rows into results/perf.csv (rows of other workload, scale,
    engine combinations are kept); called after every measurement."""
    path = os.path.join(RESULTS, "perf.csv")
    done = {(r["workload"], str(r["scale"]), r["engine"]) for r in rows}
    keep = []
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            if (r["workload"], r["scale"], r["engine"]) not in done:
                keep.append(r)
    for r in rows:
        r.setdefault("date", date)
        if not r.get("date"):
            r["date"] = date
    for r in keep + rows:
        why = viability(r)
        r["viable"] = "no: " + why if why else ("yes" if r.get("status") == "ok" else "")
    order = {n: i for i, n in enumerate(ENGINE_ORDER)}
    allrows = sorted(keep + rows, key=lambda r: (r["workload"], float(r["scale"]),
                                                 order.get(r["engine"], 99)))
    tmp = path + ".part"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)
    os.replace(tmp, path)


def write_machine(info):
    mpath = os.path.join(RESULTS, "machine.json")
    runs = json.load(open(mpath)) if os.path.exists(mpath) else []
    if isinstance(runs, dict):
        runs = [runs]
    runs.append(info)
    json.dump(runs, open(mpath, "w"), indent=1)
    print("results/perf.csv, results/machine.json written")


if __name__ == "__main__":
    sys.exit(main())
