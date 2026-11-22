"""Builds results/results.md from results/conformance.csv, results/perf.csv
and results/machine.json.

    python -m harness.report
    python -m harness.report --campaign-summary ID   # what campaign ID measured (text)
"""

import csv
import json
import os
import sys
from collections import Counter, defaultdict

from harness import RESULTS, ROOT

_HOME = os.path.expanduser("~")


def _scrub(text):
    """Local paths out of a published table: the repository root as '.'."""
    return text.replace(os.path.realpath(ROOT), ".").replace(ROOT, ".").replace(_HOME, "~")

NAMES = {"sg-java": "SPARQL-Generate", "sg-java-2.1.0": "SPARQL-Generate",
         "pysparql-generate": "", "rpt": ""}


def engine_label(engine, rs):
    """'<engine> <version>', the version being the one recorded with the
    results (the most frequent, if several)."""
    vs = Counter(r.get("version", "") for r in rs if r["engine"] == engine and r.get("version"))
    if not vs:
        return engine
    v = vs.most_common(1)[0][0]
    name = NAMES.get(engine, engine)
    return ("%s %s" % (name, v)).strip()


def rows(name):
    p = os.path.join(RESULTS, name)
    return list(csv.DictReader(open(p, newline="", encoding="utf-8"))) if os.path.exists(p) else []


def conformance_md(rs):
    out = ["## RQ1 — Conformance to the RML test suites", "",
           "Each case is solved twice by a SPARQL-Generate engine: by a hand-written "
           "query (`conformance/hand/`, mode `hand`), and by the query that "
           "`rml2sparql-generate` generates from the case's mapping (mode "
           "`translated`); an RML engine runs the mapping itself (mode `rml`). A case "
           "passes when the output is isomorphic to the expected `output.nq` (RDF "
           "dataset isomorphism), or, for a case that expects an error, when an error "
           "is raised. N/A: an invalid mapping has no hand-written counterpart; a "
           "translated case with graph maps is out of reach of `GENERATE`, whose "
           "templates hold triples (its default graph is checked).", ""]
    c = Counter((r["suite"], r["format"], r["mode"], r["engine"], r["status"]) for r in rs)
    keys = sorted({k[:4] for k in c}, key=lambda k: (k[0], k[2], k[3], k[1]))
    out.append("| suite | track | mode | engine | PASS | FAIL | N/A | TODO |")
    out.append("|---|---|---|---|---|---|---|---|")
    for k in keys:
        out.append("| %s | %s | %s | %s | %d | %d | %d | %d |" % (
            k[0], k[1], k[2], engine_label(k[3], rs),
            *(c[k + (s,)] for s in ("PASS", "FAIL", "N/A", "TODO"))))
    for eng in ("sg-java", "pysparql-generate", "rpt"):
        fails = [r for r in rs if r["status"] == "FAIL" and r["engine"] == eng]
        if not fails:
            continue
        out += ["", "Failures of %s (`%s`):" % (engine_label(eng, rs), eng), "",
                "| suite | case | mode | reason |", "|---|---|---|---|"]
        for r in fails:
            out.append("| %s | %s | %s | %s |" % (r["suite"], r["case"], r["mode"],
                                                  r["detail"].replace("|", "\\|")[:160]))
    return out


def limits(machines):
    """The limits of a run (the last recorded, else the defaults)."""
    from harness import perf, sandbox
    lim = next((m["limits"] for m in reversed(machines) if m.get("limits")), {})
    return lim.get("memory") or sandbox.DEFAULT_CAP, int(lim.get("time_s") or perf.LIMIT_TIME_S)


def _gb(cap):
    from harness import sandbox
    return "%g GB" % (sandbox.to_bytes(cap) / 2**30)


def perf_md(rs, machines):
    from harness.perf import viability
    mem, tlim = limits(machines)
    out = ["## RQ3 — Performance", "",
           "**Limits.** Every run of every engine has the same limits: %s of memory and %d "
           "min of wall time. A run over a limit is stopped: the solution is *not viable* at "
           "that size, and is neither replayed nor tried at a larger size. Runs measured "
           "before the limits were set are classified the same way, from their peak memory "
           "and time." % (_gb(mem), tlim // 60), ""]
    if machines:
        m = machines[-1]
        out += ["**Provisional timings.** Measured on %s (%s, %s CPUs, %s GB RAM, %s; %s; "
                "Python %s) on %s, while other jobs were running (load average %s before, "
                "%s after): to be re-measured on a quiet machine." % (
                    m.get("host"), m.get("cpu"), m.get("cpus"), m.get("ram_gb"), m.get("os"),
                    m.get("java"), m.get("python"), m.get("date"),
                    "/".join(m.get("loadavg", [])), "/".join(m.get("loadavg_after", []))), ""]
    out += ["Cold processes, best of the runs (wall time, start-up included) and the "
            "peak resident memory of that run; distinct triples of the output. ✓: the "
            "output is the reference output (Morph-KGC) at the smallest scale; =: same "
            "number of distinct triples as the reference at a larger scale; ✗: it "
            "differs (see the notes). Java engines: same JDK, same maximum heap.", ""]
    by_wl = defaultdict(list)
    for r in rs:
        by_wl[r["workload"]].append(r)
    for wl, wrs in by_wl.items():
        engines = []
        for r in wrs:
            if r["engine"] not in engines:
                engines.append(r["engine"])
        scales = sorted({r["scale"] for r in wrs}, key=float)
        out += ["### %s" % wl, "", "| engine | version | " + " | ".join(
            "scale %s" % s for s in scales) + " |", "|---|---|" + "---|" * len(scales)]
        notes = []
        for e in engines:
            cells, version = [], ""
            for s in scales:
                r = next((x for x in wrs if x["engine"] == e and x["scale"] == s), None)
                if r is None:
                    cells.append("")
                    continue
                version = r.get("version") or version
                why = viability(r, mem, tlim)
                if why:
                    cell = "not viable (> %s)" % (_gb(mem) if why == "memory" else "%d min" % (tlim // 60))
                    if r["status"] == "ok":
                        cell += ": %ss · %s MB" % (r["wall_s"], r["rss_mb"])
                    cells.append(cell)
                elif r["status"] == "ok":
                    mark = {"yes": " ✓", "no": " ✗", "count": " =", "reference": " (ref.)"}.get(r.get("equivalent", ""), "")
                    cells.append("%ss · %s MB · %s%s" % (r["wall_s"], r["rss_mb"], r["triples"], mark))
                else:
                    cells.append(r["status"])
                if r.get("note") and (r["status"] != "ok" or r.get("equivalent") == "no"):
                    notes.append("%s, scale %s: %s" % (e, s, r["note"][:220]))
            out.append("| %s | %s | %s |" % (e, version, " | ".join(cells)))
        if notes:
            out += [""] + ["- " + n.replace("|", "\\|") for n in notes]
        out.append("")
    return out


def campaign_summary(cid):
    """A few lines: what campaign cid measured, per workload (statuses)."""
    rs = [r for r in rows("perf.csv") if r.get("campaign") == cid]
    ms = [r for r in rows("memory.csv") if r.get("campaign") == cid]
    by = defaultdict(Counter)
    for r in rs:
        by[r["workload"]][r["status"]] += 1
    out = ["Performance rows of campaign %s: %d (%s)." % (
        cid, len(rs), ", ".join("%d %s" % (n, s) for s, n in
                                sum(by.values(), Counter()).most_common()))]
    for wl in sorted(by):
        scales = sorted({r["scale"] for r in rs if r["workload"] == wl}, key=float)
        out.append("- %s, scales %s: %s" % (wl, " ".join(scales), ", ".join(
            "%d %s" % (n, s) for s, n in by[wl].most_common())))
    if ms:
        out.append("Memory-bounded runs: %d (%s)." % (len(ms), ", ".join(
            "%s %s" % (r["engine"], r["min_heap"]) for r in ms)))
    machines = []
    mp = os.path.join(RESULTS, "machine.json")
    if os.path.exists(mp):
        machines = [m for m in json.load(open(mp)) if m.get("campaign") == cid]
    if machines:
        loads = [float(m["loadavg"][0]) for m in machines] + [
            float(m["loadavg_after"][0]) for m in machines if m.get("loadavg_after")]
        out.append("Load average (1 min) around the commands: %.2f to %.2f." % (
            min(loads), max(loads)))
    return "\n".join(out)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["--campaign-summary"]:
        print(campaign_summary(argv[1]))
        return 0
    machines = []
    mp = os.path.join(RESULTS, "machine.json")
    if os.path.exists(mp):
        machines = json.load(open(mp))
        if isinstance(machines, dict):
            machines = [machines]
    md = ["# kgc-bench — results", "",
          "Generated by `python -m harness.report` from `conformance.csv`, `perf.csv` "
          "and `machine.json`; do not edit by hand.", ""]
    md += conformance_md(rows("conformance.csv")) + [""]
    md += perf_md(rows("perf.csv"), machines)
    for extra in ("memory.csv",):
        if rows(extra):
            md += memory_md(rows(extra))
    if rows("slicing.csv"):
        md += slicing_md(rows("slicing.csv"))
    if rows("portability.csv"):
        md += portability_md(rows("portability.csv"))
    if rows("fidelity.csv"):
        md += fidelity_md(rows("fidelity.csv"))
    if rows("features.csv"):
        md += features_md(rows("features.csv"))
    if rows("translator-ab.csv"):
        md += translator_ab_md(rows("translator-ab.csv"))
    open(os.path.join(RESULTS, "results.md"), "w", encoding="utf-8").write(
        _scrub("\n".join(md)) + "\n")
    print("results/results.md written")
    return 0


def memory_md(rs):
    out = ["## Memory-bounded runs", "",
           "Smallest maximum heap (-Xmx, by bisection over powers of two) with which "
           "each Java engine completes, and its wall time and peak memory at that heap.", "",
           "| workload | scale | engine | min heap | wall s | peak MB |", "|---|---|---|---|---|---|"]
    for r in rs:
        out.append("| %s | %s | %s | %s | %s | %s |" % (r["workload"], r["scale"], r["engine"],
                                                       r["min_heap"], r["wall_s"], r["rss_mb"]))
    return out + [""]


def slicing_md(rs):
    out = ["## Positioning — semantics drift under slicing", "",
           "The same questions (`positioning/slicing/queries/`) over 24 people in CSV, JSON "
           "and XML. SPARQL Anything: with slicing, and batches of 2, 10 and 1000 slices, "
           "against `slice=false`; SPARQL-Generate: the iterator in batches of 1, 2, 10 and "
           "1000 rows, against one batch. A question changes when its multiset of solutions "
           "differs from the reference's (`python -m harness.slicing`).", "",
           "| engine | format | configuration | questions changed | which | warnings |",
           "|---|---|---|---|---|---|"]
    keys = []
    for r in rs:
        k = (r["engine"], r["version"], r["format"], r["config"])
        if k not in keys:
            keys.append(k)
    for k in keys:
        g = [r for r in rs if (r["engine"], r["version"], r["format"], r["config"]) == k]
        if not any(r["same"] for r in g):
            continue
        changed = [r["query"] for r in g if r["same"] == "no"]
        failed = [r["query"] + " (" + r["status"] + ")" for r in g if r["status"] != "ok"]
        out.append("| %s | %s | %s | %d/%d | %s | %d |" % (
            k[1], k[2], k[3], len(changed), len(g), " ".join(q[:3] for q in changed)
            + ("; not run to the end: " + ", ".join(failed) if failed else ""),
            sum(1 for r in g if r["warnings"])))
    names = sorted({r["query"] for r in rs})
    out += ["", "Questions: " + ", ".join("`%s`" % n for n in names) + ".", ""]
    return out


def translator_ab_md(rs):
    """The A/B of the translator (scripts/ab_translator.sh): the runs of A and B
    side by side, and whether they give the same distinct triples."""
    out = ["## The translator, A/B", "",
           "`scripts/ab_translator.sh`: the pinned rml2sparql-generate (A) and a newer one (B), "
           "run in the order A B B A, one run at a time under the run limits. Wall time, peak "
           "memory; ✓ when every run of A and B gives the same number of distinct triples. "
           "Provisional: shared machine.", "",
           "| workload | engine | A | B | triples |", "|---|---|---|---|---|"]
    keys = []
    for r in rs:
        k = (r.get("series", ""), r["workload"], r["scale"], r["engine"], r.get("version", ""))
        if k not in keys:
            keys.append(k)
    for k in keys:
        g = [r for r in rs
             if (r.get("series", ""), r["workload"], r["scale"], r["engine"], r.get("version", "")) == k]
        def cell(v):
            runs = [r for r in g if r["variant"] == v]
            if not runs:
                return ""
            rev = runs[0]["translator"]
            return "%s: %s" % (rev, ", ".join(
                ("%ss · %.1f GB" % (r["wall_s"], float(r["rss_mb"]) / 1024)) if r["status"] == "ok"
                else r["status"] for r in runs))
        counts = {r["triples"] for r in g if r["status"] == "ok"}
        out.append("| %s %s | %s %s | %s | %s | %s |" % (
            k[1], k[2], k[3], k[4], cell("A"), cell("B"),
            ("✓ %s" % next(iter(counts))) if len(counts) == 1 else "✗ %s" % "/".join(sorted(counts))))
    return out + [""]


def features_md(rs):
    out = ["## Positioning — feature matrix", "",
           "Minimal executable cases (`positioning/features/cases.py`), each with its input "
           "and expected output (`python -m harness.features`): pass, fail, error, not "
           "expressible (the engine has no construct for it), not run (needs a service this "
           "machine does not have).", ""]
    engines = []
    for r in rs:
        if r["engine"] not in engines:
            engines.append(r["engine"])
    versions = {r["engine"]: r["version"] for r in rs}
    out += ["| case | " + " | ".join(versions[e] for e in engines) + " |",
            "|---|" + "---|" * len(engines)]
    cases = []
    for r in rs:
        if r["case"] not in cases:
            cases.append(r["case"])
    notes = []
    for c in cases:
        cells, what = [], ""
        for e in engines:
            r = next((x for x in rs if x["case"] == c and x["engine"] == e), None)
            if r is None:
                cells.append("")
                continue
            what = r["what"]
            cells.append(r["outcome"])
            if r["outcome"] not in ("pass",) and (r["detail"] or r["note"]):
                notes.append("%s, %s: %s" % (c, versions[e], "; ".join(
                    x for x in (r["note"], r["detail"]) if x)[:220]))
            elif r["note"]:
                notes.append("%s, %s: %s" % (c, versions[e], r["note"][:220]))
        out.append("| %s (%s) | %s |" % (c, what, " | ".join(cells)))
    if notes:
        out += [""] + ["- " + n.replace("|", "\\|") for n in notes]
    return out + [""]


def fidelity_md(rs):
    out = ["## Positioning — value fidelity across releases", "",
           "Small inputs (`positioning/fidelity/cases.py`) read by every release of each "
           "engine (`python -m harness.fidelity`): ✓ every value read faithfully, ✗ some "
           "value not (the keys in parentheses), E an error; † what is read differs from "
           "the previous release.", ""]
    for eng in ("sparql-anything", "sparql-generate"):
        g = [r for r in rs if r["engine"] == eng]
        if not g:
            continue
        versions = []
        for r in g:
            if r["version"] not in versions:
                versions.append(r["version"])
        cases = []
        for r in g:
            if r["case"] not in cases:
                cases.append(r["case"])
        name = {"sparql-anything": "SPARQL Anything", "sparql-generate": "SPARQL-Generate"}[eng]
        out += ["%s:" % name, "", "| case | " + " | ".join(versions) + " |",
                "|---|" + "---|" * len(versions)]
        for c in cases:
            cells = []
            for v in versions:
                r = next((x for x in g if x["case"] == c and x["version"] == v), None)
                if r is None:
                    cells.append("")
                    continue
                cell = {"yes": "✓", "no": "✗"}.get(r["faithful"], "E")
                if r["faithful"] == "no" and r["unfaithful_keys"]:
                    cell += " (%s)" % r["unfaithful_keys"]
                if r["drift"] == "yes":
                    cell += " †"
                cells.append(cell)
            out.append("| %s | %s |" % (c, " | ".join(cells)))
        out.append("")
    last = {}
    for r in rs:
        last[(r["engine"], r["case"])] = r
    out += ["What the last releases read:", ""]
    for (eng, c), r in sorted(last.items()):
        out.append("- %s %s, %s: %s" % (eng, r["version"], c,
                                        (r["observed"] or r["detail"])[:200].replace("|", "\\|")))
    return out + [""]


def portability_md(rs):
    out = ["## Positioning — portability of SPARQL Anything queries", "",
           "SPARQL Anything queries (`positioning/portability/queries/`) run on plain SPARQL "
           "engines, on an empty dataset (`python -m harness.portability`): `same` as SPARQL "
           "Anything, `different`, `empty`, or `error`.", ""]
    engines = []
    for r in rs:
        if r["engine"] not in engines:
            engines.append(r["engine"])
    versions = {r["engine"]: r["version"] for r in rs}
    out.append("| query | " + " | ".join(versions[e] for e in engines) + " |")
    out.append("|---|" + "---|" * len(engines))
    for q in sorted({r["query"] for r in rs}):
        cells = []
        for e in engines:
            r = next((x for x in rs if x["query"] == q and x["engine"] == e), None)
            cells.append("" if r is None else "%s%s" % (
                r["outcome"], " (%s)" % r["results"] if r["results"] not in ("", "0") else ""))
        out.append("| %s | %s |" % (q, " | ".join(cells)))
    errors = {}
    for r in rs:
        if r["outcome"] == "error" and r["detail"]:
            errors.setdefault((r["engine"], r["detail"][:120]), []).append(r["query"][:3])
    if errors:
        out += ["", "Errors:", ""]
        for (e, d), qs in errors.items():
            out.append("- %s (%s): %s" % (versions[e], " ".join(qs), d.replace("|", "\\|")))
    return out + [""]


if __name__ == "__main__":
    sys.exit(main())
