"""Scores of the measurements of scripts/patches/measure.sh: PASS / cases, suite
by suite, under the published rule (an empty output is an error reported), for
every results/patched/<engine>/<variant>/conformance.csv; with --diff, the
cases whose status differs between two variants of an engine.

    python scripts/patches/summary.py [--diff ENGINE A B]
"""

import csv
import glob
import os
import sys

SUITES = ["rml-test-cases", "rml-core", "rml-io", "rml-fnml", "rml-cc", "rml-star", "rml-lv"]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "patched")


def status(row):
    # files written before the merge of main: status strict, status_empty_is_error published
    return row.get("status_empty_is_error") or row["status"]


def load(engine, variant):
    with open(os.path.join(ROOT, engine, variant, "conformance.csv"), newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["mode"] == "rml"]


def main(argv):
    if argv[:1] == ["--diff"]:
        engine, a, b = argv[1:4]
        ra = {(r["suite"], r["case"]): status(r) for r in load(engine, a)}
        rb = {(r["suite"], r["case"]): (status(r), r["detail"]) for r in load(engine, b)}
        for k in sorted(set(ra) | set(rb)):
            if ra.get(k) != rb.get(k, (None,))[0]:
                print("%-15s %-18s %s -> %s  %s" % (k + (ra.get(k), rb.get(k, ("-",))[0],
                                                       rb.get(k, ("", ""))[1][:90])))
        return 0
    print("| engine | variant | version | " + " | ".join(SUITES) + " | total |")
    print("|---" * (len(SUITES) + 4) + "|")
    for path in sorted(glob.glob(os.path.join(ROOT, "*", "*", "conformance.csv"))):
        variant = os.path.basename(os.path.dirname(path))
        engine = os.path.basename(os.path.dirname(os.path.dirname(path)))
        rows = load(engine, variant)
        cells, total = [], 0
        for s in SUITES:
            rs = [r for r in rows if r["suite"] == s]
            p = sum(status(r) == "PASS" for r in rs)
            total += p
            cells.append("%d/%d" % (p, len(rs)) if rs else "—")
        version = sorted({r["version"] for r in rows})
        print("| %s | %s | %s | %s | %d |" % (engine, variant, "; ".join(version), " | ".join(cells), total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
