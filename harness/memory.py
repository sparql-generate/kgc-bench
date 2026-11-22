"""Memory-bounded runs: the smallest maximum heap with which each Java engine
completes a workload.

    python -m harness.memory [--workload flat-csv] [--scale 1000]
                             [--engines sg-java sparql-anything sparql-anything-slice ...]
                             [--mem-cap 16G] [--campaign ID]

For each engine, the heap is searched by bisection over 64m, 128m, ... up to
75% of the memory limit of a run (12g for 16G): a run succeeds when it exits
normally and writes as many distinct triples as the run with the largest
heap. Every run has the limits of harness.perf (memory, --mem-cap, 16G; time,
--timeout, 600 s); an engine that fails at the largest heap is not viable. Writes
results/memory.csv; with --campaign ID, an engine already done in campaign
ID is not run again.
"""

import argparse
import csv
import os
import shutil
import sys

from harness import RESULTS
from harness import engines as E
from harness import workloads as W
from harness import sandbox
from harness.perf import LIMIT_TIME_S, TMP, add_cap_option, apply_cap_option, timed

HEAPS = ["64m", "128m", "256m", "512m", "1g", "2g", "4g", "8g", "16g"]

VARIANTS = {
    "sparql-anything-slice": E.SPARQLAnything("sparql-anything-slice", ["slice=true"]),
    "sparql-anything-ondisk": E.SPARQLAnything("sparql-anything-ondisk", ["ondisk=%TMP%"]),
}


def engine(name):
    return E.BY_NAME.get(name) or VARIANTS[name]


def attempt(eng, job, work, heap, timeout):
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    eng.prepare(job, work, heap)
    cmd = [c.replace("%TMP%", os.path.join(work, "ondisk")) for c in eng.command(job, work, heap)]
    os.makedirs(os.path.join(work, "ondisk"), exist_ok=True)
    status, wall, rss, err, _ = timed(cmd, timeout, cwd=work)
    triples = E.count_triples(eng.output(work), eng.out_format) if status == "ok" else None
    print("    %-6s %-8s %7.1fs %8s MB %s triples" % (heap, status, wall, rss, triples), flush=True)
    return status, wall, rss, triples


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workload", default="flat-csv")
    ap.add_argument("--scale", type=float, default=1000)
    ap.add_argument("--engines", nargs="*", default=["sg-java", "sparql-anything",
                                                     "sparql-anything-slice", "rmlmapper", "rpt"])
    ap.add_argument("--timeout", type=int, default=LIMIT_TIME_S)
    add_cap_option(ap)
    ap.add_argument("--campaign", default=os.environ.get("KGC_BENCH_CAMPAIGN"))
    args = ap.parse_args(argv)
    cap = apply_cap_option(args)
    limit = sandbox.to_bytes(cap) * 3 // 4 if cap else float("inf")
    heaps = [h for h in HEAPS if sandbox.to_bytes(h.upper()) <= limit]
    scale = int(args.scale) if float(args.scale).is_integer() else args.scale
    wl = W.ALL[args.workload]
    wl.ensure_data(scale)
    root = os.path.join(TMP, "memory", wl.name, str(scale))
    job = wl.job(scale, root)
    rows = []
    path = os.path.join(RESULTS, "memory.csv")
    previous = list(csv.DictReader(open(path))) if os.path.exists(path) else []
    for name in args.engines:
        eng = engine(name)
        if not eng.available():
            continue
        prev = next((r for r in previous if args.campaign and r.get("campaign") == args.campaign
                     and (r["workload"], r["scale"], r["engine"]) == (wl.name, str(scale), name)),
                    None)
        if prev:
            print("== %s already done in campaign %s" % (name, args.campaign), flush=True)
            rows.append(prev)
            continue
        print("== %s" % name, flush=True)
        work = os.path.join(root, name)
        # reference: the largest heap
        status, wall, rss, full = attempt(eng, job, work, heaps[-1], args.timeout)
        # the reference's count (perf.csv): an engine may write a partial output
        # and exit 0 when its heap is too small
        from harness.perf import stored_reference
        ref = stored_reference(wl.name, scale)
        if status == "ok" and ref and str(full) != str(ref.get("triples")):
            status = "wrong-output"
        if status != "ok":
            rows.append({"workload": wl.name, "scale": scale, "engine": name,
                         "min_heap": "not viable: fails at %s (%s)" % (heaps[-1], status),
                         "campaign": args.campaign or ""})
            write(rows)
            continue
        lo, hi, best = 0, len(heaps) - 1, (heaps[-1], wall, rss)
        while lo < hi:
            mid = (lo + hi) // 2
            s, w, r, t = attempt(eng, job, work, heaps[mid], args.timeout)
            if s == "ok" and t == full:
                hi, best = mid, (heaps[mid], w, r)
            else:
                lo = mid + 1
        rows.append({"workload": wl.name, "scale": scale, "engine": name,
                     "min_heap": best[0], "wall_s": best[1], "rss_mb": best[2],
                     "triples": full, "campaign": args.campaign or ""})
        write(rows)
    print("results/memory.csv written")
    return 0


def write(rows):
    """Merge into results/memory.csv (other combinations kept)."""
    path = os.path.join(RESULTS, "memory.csv")
    keep = []
    if os.path.exists(path):
        done = {(r["workload"], str(r["scale"]), r["engine"]) for r in rows}
        keep = [r for r in csv.DictReader(open(path)) if
                (r["workload"], r["scale"], r["engine"]) not in done]
    with open(path + ".part", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["workload", "scale", "engine", "min_heap",
                                          "wall_s", "rss_mb", "triples", "campaign"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(keep + rows)
    os.replace(path + ".part", path)


if __name__ == "__main__":
    sys.exit(main())
