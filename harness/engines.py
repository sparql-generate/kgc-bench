"""The engines under test, each run as a cold, uniform subprocess.

An engine is given a *job* (a dict built by a workload: the data directory,
the RML mapping, the SPARQL-Generate query, the SPARQL Anything query, the
base IRI) and a fresh working directory; it returns the command to run and
the file it writes. harness.perf times the command under /usr/bin/time -v.

Java engines all run on the JDK of versions.env (JAVA_HOME_BENCH) with the
same maximum heap (--xmx, 16g by default), so that peak memory compares
like with like. Every process (preparation included) runs in a
memory-capped scope (harness.sandbox).
"""

import os
import shutil
import subprocess
import sys

from harness import ENGINES as ENGINE_DIR, RML2SG, RML2SG_TAU, VERSIONS, java, rdfcompare, sandbox
from harness import rmlengines
from harness.conformance import install_translator
from harness import sg as sgcli

PY = sys.executable
# the interpreter of pysparql-generate: its dependencies (DuckDB 2) may differ from
# those of the Python engines of the benchmark (Morph-KGC pins its own DuckDB 1.x,
# with which every CSV query of the export fails: "no such column in the header").
# KGC_BENCH_PYSG_PYTHON when set; else the harness's own Python if its DuckDB
# satisfies the export, else the venv of REPRODUCE.md (~/.venvs/pysg) if it does
# (pysg_python); otherwise the harness's, and pysg_interpreter_problem says why.
PYSG_PY_ENV = os.environ.get("KGC_BENCH_PYSG_PYTHON")
PYSG_PY_REPRODUCE = os.path.expanduser(os.path.join("~", ".venvs", "pysg", "bin", "python"))
# pysparql-generate: the commit exported by scripts/build_pysparql_generate.sh
# (KGC_BENCH_PYSG_DIR: another export, for an A/B measurement)
PYSG_DIR = os.environ.get("KGC_BENCH_PYSG_DIR") or os.path.join(ENGINE_DIR, "pysparql-generate")


def pysg_version():
    try:
        return "pysparql-generate " + open(os.path.join(PYSG_DIR, "COMMIT")).read().strip()
    except OSError:
        return ""


_PYSG_CHECKED = {}


def _duckdb_problem(python):
    """Why the interpreter `python` cannot run the export, or "": its DuckDB must
    satisfy the export's requirement (pysparql-generate 0.3.0 and later:
    duckdb>=2.0)."""
    if python in _PYSG_CHECKED:
        return _PYSG_CHECKED[python]
    import re as _re
    need = None
    try:
        m = _re.search(r'"duckdb\s*>=\s*([0-9.]+)"', open(os.path.join(PYSG_DIR, "pyproject.toml")).read())
        need = m.group(1) if m else None
    except OSError:
        pass
    try:
        r = subprocess.run([python, "-c", "import duckdb; print(duckdb.__version__)"],
                           capture_output=True, text=True)
    except OSError as e:
        _PYSG_CHECKED[python] = why = "%s: %s" % (python, e)
        return why
    have = r.stdout.strip()
    why = ""
    if r.returncode != 0:
        why = "%s: no duckdb (KGC_BENCH_PYSG_PYTHON: a venv of its own)" % python
    elif need and tuple(int(x) for x in have.split(".")[:2]) < tuple(int(x) for x in need.split(".")[:2]):
        why = ("%s has duckdb %s, pysparql-generate needs >= %s: set KGC_BENCH_PYSG_PYTHON to the "
               "Python of a venv of its own (REPRODUCE.md)" % (python, have, need))
    _PYSG_CHECKED[python] = why
    return why


_PYSG_PY = []


def pysg_python():
    """The interpreter that runs the exported pysparql-generate (PYSG_PY_ENV, or the
    first of the harness's Python and PYSG_PY_REPRODUCE whose DuckDB satisfies the
    export, else the harness's)."""
    if not _PYSG_PY:
        if PYSG_PY_ENV:
            _PYSG_PY.append(PYSG_PY_ENV)
        else:
            ok = [p for p in (PY, PYSG_PY_REPRODUCE) if os.path.exists(p) and not _duckdb_problem(p)]
            _PYSG_PY.append(ok[0] if ok else PY)
    return _PYSG_PY[0]


def pysg_interpreter_problem():
    """Why the interpreter of pysparql-generate (pysg_python) cannot run the export,
    or ""."""
    return _duckdb_problem(pysg_python())


def require_pysg_interpreter():
    """Stop with a clear message when the interpreter of pysparql-generate cannot
    run the export (instead of an error in every case)."""
    why = pysg_interpreter_problem()
    if why:
        raise SystemExit("pysparql-generate: " + why)


def pysg_command():
    """The command that runs the exported pysparql-generate (its src/ first on
    the path, ahead of any editable install)."""
    return ["env", "PYTHONPATH=" + os.path.join(os.path.realpath(PYSG_DIR), "src"),
            pysg_python(), "-m", "sparql_generate.cli"]


def _jar(name):
    return os.path.join(ENGINE_DIR, name)


def link_data(job, work):
    """Symlink the data files into the working directory (the SPARQL-Generate
    CLI maps the files of its directory to IRIs under -b)."""
    os.makedirs(work, exist_ok=True)
    for f in os.listdir(job["data"]):
        src = os.path.join(job["data"], f)
        dst = os.path.join(work, f)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.symlink(src, dst)


class Engine:
    name = ""
    lang = ""          # what it reads: "rml", "sg" (SPARQL-Generate), "sa" (SPARQL Anything)
    out_format = "nt"  # format of its output file
    python = False     # a Python process

    def version(self):
        return ""

    def available(self):
        return True

    def prepare(self, job, work, xmx):
        """Untimed preparation (configuration files, translation)."""

    def command(self, job, work, xmx):
        raise NotImplementedError

    def output(self, work):
        return os.path.join(work, "out." + ("ttl" if self.out_format == "turtle" else "nt"))

    def collect(self, work):
        """Untimed, after a successful run: gather the output into output(work)
        (RMLStreamer writes part files)."""

    def discard(self, work):
        """After a failed run: remove what the engine wrote besides output(work)."""


class SGJava(Engine):
    lang = "sg"

    def __init__(self, name="sg-java", jar_key="sg-java", translated=False, stream=True,
                 translator=None):
        self.name, self.jar_key, self.translated = name, jar_key, translated
        self.stream = stream
        # the copy of rml2sparql-generate (default: the pinned optimised translation, RML2SG)
        self.translator = translator or RML2SG
        if translated:
            self.lang = "rml"

    @property
    def out_format(self):
        """N-Triples, except the streamed output before 2.2.3: Turtle, one
        triple per line (2.2.3 streams real N-Triples with -s -fo NT)."""
        if self.stream and sgcli.version_tuple(self.jar_key) < (2, 2, 3):
            return "turtle"
        return "nt"

    def version(self):
        v = sgcli.jar_label(self.jar_key)
        if self.translated:
            v += " + rml2sparql-generate " + _git_head(self.translator)
        return v

    def available(self):
        return os.path.exists(sgcli.jar_path(self.jar_key)) and (
            not self.translated or os.path.isdir(self.translator))

    def prepare(self, job, work, xmx):
        link_data(job, work)
        if not self.translated:
            shutil.copy(job["sg_query"], os.path.join(work, "query.rqg"))
            return
        translate_mapping(job, work, self.name, self.translator)

    def command(self, job, work, xmx):
        base = job["rml_base"] if self.translated else job["sg_base"]
        if not self.stream:
            return sgcli.command(self.jar_key, work, "query.rqg", "out.nt", base=base,
                                 fmt="NT", log="ERROR", xmx=xmx)
        if self.out_format == "nt":
            return sgcli.command(self.jar_key, work, "query.rqg", "out.nt", base=base,
                                 fmt="NT", log="ERROR", xmx=xmx) + ["-s"]
        return sgcli.command(self.jar_key, work, "query.rqg", "out.ttl",
                             base=base, log="ERROR", xmx=xmx) + ["-s"]


def translation_timeout():
    """The time limit of a translation, in seconds: KGC_BENCH_TRANSLATION_TIMEOUT or 600."""
    return int(os.environ.get("KGC_BENCH_TRANSLATION_TIMEOUT") or 600)


def translate_mapping(job, work, name, translator=None):
    """rml2sparql-generate (the copy translator, default the pinned one), run
    by the Java engine, writes work/query.rqg from the job's mapping: untimed,
    its time noted by harness.perf. Its time limit, KGC_BENCH_TRANSLATION_TIMEOUT
    (default 600 s), is apart from the run's: gtfs-feeds at K = 1000 has 13 000
    triples maps, about 15 min of translation with 0.5.4."""
    tdir = os.path.join(work, "translation")
    os.makedirs(os.path.join(tdir, "dataset"), exist_ok=True)
    shutil.copy(job["rml_relative"], os.path.join(tdir, "dataset", "default.ttl"))
    install_translator(tdir, translator)
    r = sgcli.run("sg-java", tdir, "rml2sparql-generate.rqg", "generated.rqg",
                  base=job["rml_base"], timeout=translation_timeout())
    if not r["ok"]:
        raise RuntimeError("translation failed: " + r["error"])
    shutil.copy(r["output"], os.path.join(work, "query.rqg"))
    job.setdefault("translation_s", {})[name] = round(r["wall_s"], 2)


class PySG(Engine):
    python = True
    name = "pysparql-generate"
    lang = "sg"

    def version(self):
        return pysg_version()

    def available(self):
        if not os.path.isdir(os.path.join(PYSG_DIR, "src", "sparql_generate")):
            self.unavailable_reason = "no export (scripts/build_pysparql_generate.sh)"
            return False
        why = pysg_interpreter_problem()
        if why:
            self.unavailable_reason = why
            return False
        return True

    def prepare(self, job, work, xmx):
        link_data(job, work)
        shutil.copy(job["sg_query"], os.path.join(work, "query.rqg"))

    def command(self, job, work, xmx):
        return pysg_command() + ["-d", work, "-q", "query.rqg", "-b", job["sg_base"],
                                 "-o", os.path.join(work, "out.nt"), "-l", "ERROR"]


class PySGTranslated(PySG):
    """pysparql-generate on the query that rml2sparql-generate generates from
    the official mapping (the translation is run by the Java engine)."""
    name = "pysparql-generate-translated"
    lang = "rml"

    def __init__(self, name="pysparql-generate-translated", translator=None):
        self.name, self.translator = name, translator or RML2SG

    def version(self):
        return pysg_version() + " + rml2sparql-generate " + _git_head(self.translator)

    def available(self):
        return super().available() and os.path.isdir(self.translator)

    def prepare(self, job, work, xmx):
        link_data(job, work)
        translate_mapping(job, work, self.name, self.translator)

    def command(self, job, work, xmx):
        return pysg_command() + ["-d", work, "-q", "query.rqg", "-b", job["rml_base"],
                                 "-o", os.path.join(work, "out.nt"), "-l", "ERROR"]


class MorphKGC(Engine):
    """Morph-KGC with its defaults (morph-kgc), or with number_of_processes
    set (morph-kgc-4p: 4 worker processes instead of its default, twice the
    number of CPUs, 32 here). Its workers are processes: the peak memory is
    their sum (harness.perf.timed), and with 32 of them GTFS scale 100 goes over
    the 16 GB limit (README, "Settings")."""
    python = True
    lang = "rml"

    def __init__(self, name="morph-kgc", processes=None):
        self.name, self.processes = name, processes

    def version(self):
        return VERSIONS.get("MORPH_KGC_VERSION", "")

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        procs = "number_of_processes=%d\n" % self.processes if self.processes else ""
        with open(os.path.join(work, "config.ini"), "w") as f:
            f.write("[CONFIGURATION]\noutput_file=%s\noutput_format=N-TRIPLES\n"
                    "logging_level=ERROR\n%s\n[DataSource1]\nmappings=%s\n"
                    % (os.path.join(work, "out.nt"), procs, job["rml_absolute"]))

    def command(self, job, work, xmx):
        return [PY, "-m", "morph_kgc", os.path.join(work, "config.ini")]


class RMLMapper(Engine):
    """-d: duplicates removed, as every other engine of the benchmark does by
    default, and as the KGCW Challenge tool and KROWN run it (README, "Settings")."""
    name = "rmlmapper"
    lang = "rml"

    def version(self):
        return VERSIONS.get("RMLMAPPER_VERSION", "")

    def available(self):
        return os.path.exists(_jar("rmlmapper-%s.jar" % self.version()))

    def command(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        return [java(), "-Xmx" + xmx, "-jar", _jar("rmlmapper-%s.jar" % self.version()),
                "-m", job["rml_absolute"], "-o", os.path.join(work, "out.nt"),
                "-s", "ntriples", "-d"]


class SDMRDFizer(Engine):
    python = True
    name = "sdm-rdfizer"
    lang = "rml"

    def version(self):
        return VERSIONS.get("SDM_RDFIZER_VERSION", "")

    def available(self):
        try:
            import rdfizer  # noqa: F401
            return True
        except Exception as e:
            # e.g. pyodbc without the system library libodbc.so.2 (unixODBC)
            self.unavailable_reason = "import rdfizer: %s: %s" % (type(e).__name__, e)
            return False

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "config.ini"), "w") as f:
            f.write("[default]\nmain_directory: %s\n\n[datasets]\nnumber_of_datasets: 1\n"
                    "output_folder: %s\nall_in_one_file: no\nremove_duplicate: yes\n"
                    "enrichment: yes\nname: out\nordered: no\nlarge_file: false\n\n"
                    "[dataset1]\nname: out\nmapping: %s\n"
                    % (job["data"], work, job["rml_absolute"]))

    def command(self, job, work, xmx):
        return [PY, "-m", "rdfizer", "-c", os.path.join(work, "config.ini")]


class SPARQLAnything(Engine):
    name = "sparql-anything"
    lang = "sa"

    def __init__(self, name="sparql-anything", options=()):
        self.name, self.options = name, list(options)

    def version(self):
        return VERSIONS.get("SPARQL_ANYTHING_VERSION", "")

    def available(self):
        return os.path.exists(_jar("sparql-anything-%s.jar" % self.version()))

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        q = open(job["sa_query"], encoding="utf-8").read().replace("%DATA%", job["data"])
        open(os.path.join(work, "query.sparql"), "w", encoding="utf-8").write(q)

    def command(self, job, work, xmx):
        cmd = [java(), "-Xmx" + xmx, "-jar", _jar("sparql-anything-%s.jar" % self.version()),
               "-q", os.path.join(work, "query.sparql"), "-f", "NT",
               "-o", os.path.join(work, "out.nt")]
        for o in self.options:
            cmd += ["-c", o]
        return cmd


class RPT(Engine):
    """RDF Processing Toolkit (C. Stadler): RML translated to SPARQL CONSTRUCT
    queries over Jena ARQ with source functions (rpt rmltk rml to sparql),
    then executed (rpt integrate)."""
    name = "rpt"
    lang = "rml"

    def version(self):
        return VERSIONS.get("RPT_VERSION", "")

    def available(self):
        return os.path.exists(_jar("rpt-%s.jar" % self.version()))

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "queries.rq"), "w") as f:
            r = sandbox.run([java(), "-jar", _jar("rpt-%s.jar" % self.version()),
                             "rmltk", "rml", "to", "sparql", job["rml_absolute"]],
                            600, stdout=f)
        # the translation RML -> SPARQL, untimed in the run, published apart
        job.setdefault("translation_s", {})[self.name] = round(r["wall_s"], 2)
        if r["status"] != "ok":
            raise RuntimeError("rpt translation failed (%s): %s" % (r["status"],
                                                                    r["stderr"][-300:]))

    def command(self, job, work, xmx):
        return ["sh", "-c", "%s -Xmx%s -jar %s integrate %s --out-format nt > %s" % (
            java(), xmx, _jar("rpt-%s.jar" % self.version()),
            os.path.join(work, "queries.rq"), os.path.join(work, "out.nt"))]


class NewRML(Engine):
    """RocketRML, FlexRML, BURP, RMLStreamer (harness.rmlengines), on the RML
    mapping, with their default options; N-Triples output (N-Quads for
    RocketRML and RMLStreamer, the same lines without graph)."""
    lang = "rml"

    def __init__(self, name):
        self.name = name

    def version(self):
        return rmlengines.version(self.name)

    def available(self):
        return rmlengines.available(self.name)

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        if self.name == "burp":
            # BURP reads only the RML of the W3C CG: the mapping converted, untimed
            from harness.workloads import to_rml_core
            to_rml_core(job["rml_absolute"], os.path.join(work, "mapping-core.rml.ttl"))

    def mapping(self, job, work):
        return os.path.join(work, "mapping-core.rml.ttl") if self.name == "burp" else job["rml_absolute"]

    def command(self, job, work, xmx):
        out = os.path.join(work, "parts" if self.name == "rmlstreamer" else "out.nt")
        return rmlengines.command(self.name, self.mapping(job, work), out, heap=xmx,
                                  parallelism=rmlengines.RMLSTREAMER_PARALLELISM
                                  if self.name == "rmlstreamer" else None)

    def collect(self, work):
        if self.name == "rmlstreamer":
            rmlengines.merge_parts(os.path.join(work, "parts"), self.output(work))

    def discard(self, work):
        p = os.path.join(work, "parts")
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.exists(p):
            os.remove(p)


class OwnLanguage(Engine):
    """An engine with a mapping language of its own (ShExML), on a GTFS mapping
    written in it (workloads/gtfs/, generated by scripts/gtfs_mappings.py) and
    checked by the same output check as the others. %DATA% in the mapping is the
    data directory, %MAPPINGS% the directory of the mapping."""
    lang = "own"

    def __init__(self, name, key):
        self.name, self.key = name, key

    def version(self):
        return rmlengines.version(self.name)

    def available(self):
        return rmlengines.available(self.name)

    def prepare(self, job, work, xmx):
        os.makedirs(work, exist_ok=True)
        src = job[self.key]
        text = open(src, encoding="utf-8").read().replace("%DATA%", job["data"]).replace(
            "%MAPPINGS%", os.path.dirname(os.path.abspath(src)))
        open(os.path.join(work, os.path.basename(src)), "w", encoding="utf-8").write(text)

    def command(self, job, work, xmx):
        m = os.path.join(work, os.path.basename(job[self.key]))
        return [java(), "-Xmx" + xmx, "-jar", rmlengines.path("shexml"), "-m", m,
                "-f", "N-Triples", "-o", self.output(work)]


def _git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


ALL = [SGJava(), SGJava("sg-java-nostream", stream=False), 
       SGJava("sg-java-translated", "sg-java", translated=True),
       # the direct translation (RML2SG_TAU_COMMIT) against the optimised one (the pinned translator)
       SGJava("sg-java-translated-tau", "sg-java", translated=True, translator=RML2SG_TAU),
       PySG(), PySGTranslated(), PySGTranslated("pysparql-generate-translated-tau", RML2SG_TAU), MorphKGC(), MorphKGC("morph-kgc-4p", 4), RMLMapper(), SDMRDFizer(), SPARQLAnything(), RPT()] + [
           NewRML(n) for n in rmlengines.NEW_RML_ENGINES] + [
           OwnLanguage("shexml", "shexml_mapping")]
BY_NAME = {e.name: e for e in ALL}


def count_triples(path, fmt):
    """Distinct triples of an output file, by lines (Turtle of the streaming
    writer: one triple per line, after the @prefix/@base lines)."""
    if not path or not os.path.exists(path):
        return None
    if fmt == "turtle":
        return rdfcompare.count_distinct_lines(
            path, "grep -v '^@prefix\\|^@base\\|^[[:space:]]*$' %s" % rdfcompare._q(path))
    return rdfcompare.count_quads(path)
