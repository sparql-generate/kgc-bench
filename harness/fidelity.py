"""Value fidelity and version drift (positioning, argument 9): do the engines
read the values of their inputs faithfully, and does what they read change
from one release to the next?

    python -m harness.fidelity [--mem-cap 4G]

The cases of positioning/fidelity/cases.py (JSON numbers, null and empty
containers, keys; XML mixed content, namespace, CDATA, xml:lang, spaces; CSV
quoting) are run on every release of engines/versions/ (scripts/
fetch_versions.sh): SPARQL Anything 0.8.2 to 1.3.0, SPARQL-Generate 2.0.9 to
2.2.2. For each key of a case: the value read (lexical form, datatype or
language), and whether it is the faithful one; a case drifts at a release
when what is read differs from the previous release.

Writes results/fidelity.csv; intermediate files under results/raw/fidelity/.
"""

import argparse
import csv
import os
import re
import shutil
import sys
import urllib.parse

from harness import ENGINES, RESULTS, ROOT, java, sandbox

SCEN = os.path.join(ROOT, "positioning", "fidelity")
RAW = os.path.join(RESULTS, "raw", "fidelity")
VERSIONS_DIR = os.path.join(ENGINES, "versions")
XSD = "http://www.w3.org/2001/XMLSchema#"
_ERROR = re.compile(r"(^|\s|\[)(ERROR|FATAL)(\]|\s)|Exception in thread|^Caused by:", re.M)


def releases():
    """[(engine, version, jar)], oldest first."""
    out = []
    for f in os.listdir(VERSIONS_DIR):
        m = re.match(r"sparql-(anything|generate)-v?([\d.]+)\.jar$", f)
        if m:
            out.append(("sparql-anything" if m.group(1) == "anything" else "sparql-generate",
                        m.group(2), os.path.join(VERSIONS_DIR, f)))
    return sorted(out, key=lambda r: (r[0], [int(x) for x in r[1].split(".")]))


def run(engine, jar, case, data, work, timeout):
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "out.json")
    if engine == "sparql-anything":
        q = os.path.join(work, "query.rq")
        open(q, "w", encoding="utf-8").write(case["sa"].replace("%DATA%", data))
        cmd = [java(), "-jar", jar, "-q", q, "-f", "JSON", "-o", out]
    else:
        src = os.path.join(data, case["file"])
        dst = os.path.join(work, case["file"])
        if not os.path.exists(dst):
            os.symlink(src, dst)
        open(os.path.join(work, "query.rqg"), "w", encoding="utf-8").write(case["sg"])
        cmd = [java(), "-jar", jar, "-d", work, "-q", "query.rqg", "-o", "out.json",
               "-fo", "JSON", "-l", "WARN", "-b", "http://example.org/"]
    r = sandbox.run(cmd, timeout, cwd=work)
    return r, out


def pairs(path, keys=None):
    """[(key term, value term)] of a results file: the (?k, ?v) columns, or
    one column ?v1 ... ?vn per key of keys."""
    import json
    res = json.load(open(path, encoding="utf-8"))
    out = []
    for b in res["results"]["bindings"]:
        if keys:
            for i, k in enumerate(keys):
                out.append((("literal", k, None, None), _t(b.get("v%d" % (i + 1)))))
        else:
            out.append((_t(b.get("k")), _t(b.get("v"))))
    return out


def _t(t):
    if t is None:
        return None
    return (t["type"].replace("typed-literal", "literal"), t["value"], t.get("datatype"),
            t.get("xml:lang"))


def observed(prs):
    """{key: sorted list of 'lexical^^datatype' / 'lexical@lang' / '(node)'}."""
    out = {}
    for k, v in prs:
        n = 1
        key = urllib.parse.unquote(k[1]) if k else ""
        if v is None:
            val = "(unbound)"
        elif v[0] != "literal":
            val = "(%s)" % v[0]
        else:
            val = v[1]
            if v[2] and v[2] != XSD + "string":
                val += "^^" + v[2].replace(XSD, "xsd:")
            elif v[3]:
                val += "@" + v[3]
        out.setdefault(key, []).extend([val] * n)
    return {k: sorted(vs) for k, vs in out.items()}


def faithful(expected, obs):
    """(yes/no, the keys that are not faithful)."""
    bad = []
    for k, exp in expected.items():
        got = [v for v in obs.get(k, []) if v != "(unbound)"]
        if exp is None:
            ok = not got or got == [""]
        elif exp == "*":
            ok = bool(got)
        elif isinstance(exp, set):
            ok = set(got) == exp
        elif isinstance(exp, tuple):
            lex, dt = exp
            ok = len(got) == 1 and _same_number(got[0], lex, dt)
        else:
            ok = len(got) == 1 and got[0].split("^^")[0] == exp
        if not ok:
            bad.append(k)
    return ("yes" if not bad else "no"), bad


def _same_number(got, lex, dt):
    """The same value, and a datatype of the same kind (integer types for an
    integer, xsd:decimal for a decimal, xsd:double for an exponent)."""
    from decimal import Decimal, InvalidOperation
    val, _, gdt = got.partition("^^")
    kinds = {"integer": ("xsd:integer", "xsd:long", "xsd:int", "xsd:short", "xsd:byte"),
             "decimal": ("xsd:decimal",), "double": ("xsd:double", "xsd:float"),
             "boolean": ("xsd:boolean",)}
    if gdt not in kinds[dt]:
        return False
    if dt == "boolean":
        return val == lex
    try:
        return Decimal(val) == Decimal(lex)
    except InvalidOperation:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mem-cap")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    sys.path.insert(0, SCEN)
    import cases as C
    shutil.rmtree(RAW, ignore_errors=True)
    data = os.path.join(RAW, "data")
    os.makedirs(data)
    for c in C.CASES:
        open(os.path.join(data, c["file"]), "w", encoding="utf-8").write(c["data"])
    rows = []
    previous = {}
    for engine, version, jar in releases():
        for c in C.CASES:
            q = c["sa"] if engine == "sparql-anything" else c["sg"]
            if not q:
                continue
            work = os.path.join(RAW, engine, version, c["name"])
            r, out = run(engine, jar, c, data, work, args.timeout)
            log = r["stderr"] + r["stdout"]
            obs, ok, bad, detail = {}, "", [], ""
            if r["status"] == "ok" and os.path.exists(out) and not _ERROR.search(log):
                try:
                    obs = observed(pairs(out, None if engine == "sparql-anything"
                                         else c.get("sg_keys")))
                    ok, bad = faithful(c["expected"], obs)
                    status = "ok"
                except Exception as e:
                    status, detail = "error", "output: %s" % str(e)[:150]
            else:
                status = "error" if r["status"] == "ok" else r["status"]
                m = _ERROR.search(log)
                detail = (log[m.start():] if m else log).strip().splitlines()[0][:200] \
                    if log.strip() else ""
            text = "; ".join("%s=%s" % (k, "|".join(v)) for k, v in sorted(obs.items()))
            key = (engine, c["name"])
            drift = "" if key not in previous else ("yes" if previous[key] != (status, text) else "no")
            previous[key] = (status, text)
            rows.append({"engine": engine, "version": version, "case": c["name"],
                         "status": status, "faithful": ok, "unfaithful_keys": " ".join(bad),
                         "drift": drift, "observed": text.replace("\n", "\\n"),
                         "detail": detail.replace(data, "%DATA%").replace(RAW, "<raw>")})
            print("%-16s %-7s %-20s %-7s %-4s %-5s %s" % (
                engine, version, c["name"], status, ok, drift, (text or detail)[:110].replace("\n", "\\n")),
                flush=True)
    path = os.path.join(RESULTS, "fidelity.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["engine", "version", "case", "status", "faithful",
                                          "unfaithful_keys", "drift", "observed", "detail"])
        w.writeheader()
        w.writerows(rows)
    print("results/fidelity.csv written (%d rows)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
