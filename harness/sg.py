"""Running the SPARQL-Generate Java engine through its command-line interface.

The CLI is the engine's public interface, so the benchmark uses it as a user
would. Three of its traits shape this module:

- the output path (``-o``) is resolved against the working directory (``-d``),
  even when absolute: outputs are always written inside the working directory;
- an execution error is logged, but the exit code stays 0: errors are
  detected in the log (``ERROR`` lines, Java exceptions);
- ``-b <base>`` maps every file of the working directory to ``<base><path>``,
  which is how queries refer to their sources (``SOURCE <student.csv>``);
- a named query (``TEMPLATE <t.rqg>(...)``) resolves its own relative IRIs
  against the process's current directory, not against ``-b``: the engine is
  started from the working directory.
"""

import hashlib
import os
import re
import zipfile

from harness import ENGINES, VERSIONS, java, sandbox

# engine label -> JAR (engines/, see scripts/fetch_engines.sh and
# scripts/build_sparql_generate.sh). sg-java is the release pinned in
# versions.env; KGC_BENCH_SG_JAR=head runs the last local build instead, or
# KGC_BENCH_SG_JAR=<file> any JAR of engines/.
RELEASE_JAR = "sparql-generate-%s.jar" % VERSIONS.get("SPARQL_GENERATE_VERSION", "")
_SG_JAR = os.environ.get("KGC_BENCH_SG_JAR", "")
JARS = {
    "sg-java": {"": RELEASE_JAR, "head": "sparql-generate-head.jar"}.get(_SG_JAR, _SG_JAR),
    "sg-java-2.1.0": "sparql-generate-%s.jar" % VERSIONS.get("SPARQL_GENERATE_RELEASE", "2.1.0"),
}
_POM = "META-INF/maven/fr.mines-stetienne.ci.sparql-generate/sparql-generate-jena/pom.properties"

_ERROR = re.compile(r"(^|\s)(ERROR|FATAL)\s|Exception in thread|^Caused by:", re.M)


def jar_path(engine):
    return os.path.join(ENGINES, JARS.get(engine, ""))


_labels = {}


def jar_label(engine):
    """The version of the engine actually run, read from the JAR: '2.2.2
    (release)' for the pinned release asset (checksum of versions.env),
    '<version> <branch> <commit>' for a local build."""
    path = os.path.realpath(jar_path(engine))
    if path in _labels:
        return _labels[path]
    try:
        with zipfile.ZipFile(path) as z:
            v = re.search(r"version=(\S+)", z.read(_POM).decode()).group(1)
    except (KeyError, OSError, AttributeError, zipfile.BadZipFile):
        v = os.path.basename(path)
    txt = jar_path(engine) + ".txt"
    if os.path.exists(txt):
        label = "%s %s" % (v, open(txt).read().strip())
    elif os.path.basename(path) == RELEASE_JAR and _sha256(path) == VERSIONS.get(
            "SPARQL_GENERATE_SHA256"):
        label = "%s (release)" % v
    elif os.path.basename(path) == JARS["sg-java-2.1.0"]:
        label = "%s (release)" % v
    else:
        label = "%s (%s)" % (v, os.path.basename(path))
    _labels[path] = label
    return label


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def version_tuple(engine):
    """(2, 2, 3) for a JAR labelled '2.2.3 ...', () if unknown."""
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", jar_label(engine))
    return tuple(int(x) for x in m.groups()) if m else ()


# a GRAPH block in a GENERATE template: GRAPH <iri>, GRAPH ?var, GRAPH ?{ ... },
# outside comments (a query generates quads; SPARQL-Generate 2.4.0 and later)
_GRAPH = re.compile(r"^[^#\n]*\bGRAPH\s*(<|\?|\$)", re.M | re.I)


def output_format(query_text, triples="NT"):
    """The output format to ask of a GENERATE query: N-Quads when it has GRAPH
    blocks (named graphs, which N-Triples cannot hold), else ``triples``."""
    return "NQUADS" if _GRAPH.search(query_text) else triples


_pysg_options = {}


def fail_on_missing(engine):
    """The CLI option that makes a missing document an error (exit code 1)
    instead of a warning: --fail-on-missing, from SPARQL-Generate 2.2.3 on,
    and in pysparql-generate when its CLI has it."""
    if engine.startswith("sg-java"):
        return ["--fail-on-missing"] if version_tuple(engine) >= (2, 2, 3) else []
    if engine == "pysparql-generate":
        from harness.engines import pysg_command, pysg_version
        v = pysg_version()
        if v not in _pysg_options:
            r = sandbox.run(pysg_command() + ["--help"], 60)
            _pysg_options[v] = "--fail-on-missing" in r["stdout"] + r["stderr"]
        return ["--fail-on-missing"] if _pysg_options[v] else []
    return []


def command(engine, workdir, query, output, base=None, fmt=None, log="WARN",
            xmx=None, extra=()):
    if engine == "pysparql-generate":
        # the Python engine: same options; -o absolute (its -o is relative to -d)
        from harness.engines import pysg_command
        cmd = pysg_command() + ["-d", workdir, "-q", query, "-o", os.path.join(workdir, output),
                                "-l", log]
        if base:
            cmd += ["-b", base]
        if fmt:
            cmd += ["-fo", fmt]
        return cmd + list(extra)
    cmd = [java()]
    if xmx:
        cmd.append("-Xmx" + xmx)
    cmd += ["-jar", jar_path(engine), "-d", workdir, "-q", query,
            "-o", output, "-l", log]
    if base:
        cmd += ["-b", base]
    if fmt:
        cmd += ["-fo", fmt]
    return cmd + list(extra)


def run(engine, workdir, query, output, base=None, fmt=None, timeout=300,
        log="WARN", xmx=None, extra=()):
    """Run one query, in a memory-capped scope (harness.sandbox); return a
    dict with ok, error (str), wall_s, output (absolute path)."""
    cmd = command(engine, workdir, query, output, base, fmt, log, xmx, extra)
    r = sandbox.run(cmd, timeout, cwd=workdir)
    if r["status"] == "timeout":
        return {"ok": False, "error": "timeout (%ds)" % timeout,
                "wall_s": timeout, "output": None}
    if r["status"] == "oom":
        return {"ok": False, "error": "killed at the memory cap (%s)" % r["mem_cap"],
                "wall_s": r["wall_s"], "output": None}
    wall = r["wall_s"]
    err = r["stderr"] + r["stdout"]
    m = _ERROR.search(err)
    out = os.path.join(workdir, output)
    if r["returncode"] != 0 or m:
        line = err[m.start():].strip().splitlines()[0] if m else err.strip()[-300:]
        return {"ok": False, "error": _clean(line), "wall_s": wall,
                "output": out, "log": err}
    return {"ok": True, "error": "", "wall_s": wall, "output": out, "log": err}


def _clean(line):
    line = re.sub(r"^\S+ main ", "", line)
    return line[:300]
