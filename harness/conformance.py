"""RQ1 — conformance of SPARQL-Generate and of RML engines to the official
RML test suites, judged by RDF dataset isomorphism with each case's
expected output.

    python -m harness.conformance [--suites rml-test-cases rml-core rml-io ...]
                                  [--modes hand translated rml]
                                  [--engines sg-java pysparql-generate rpt morph-kgc ...]
                                  [--only RMLTC0001a-CSV ...] [--jobs 2] [--mem-cap 16G]

Suites: RMLio/rml-test-cases (CSV, JSON, XML tracks), and the test cases of
the W3C KG-Construct CG specifications: rml-core, and the modules rml-io
(sources and targets), rml-fnml (functions), rml-cc (collections and
containers), rml-star (RDF-star), rml-lv (logical views).

Two ways for a SPARQL-Generate engine (sg-java, sg-java-2.1.0,
pysparql-generate) to solve a case, both reported:

hand        a query written by hand, conformance/hand/<suite>/<case>.rqg;
translated  the case's RML mapping translated by rml2sparql-generate (a
            SPARQL-Generate query, ../rml-to-sparql-generate), then the
            generated query run on the case's sources;

and one for an RML engine (rpt, morph-kgc, rmlmapper, sdm-rdfizer, rocketrml,
flexrml, burp, rmlstreamer):

rml         the engine runs the case's mapping itself, in a directory that
            holds the mapping and the case's input documents (never its
            expected outputs), with its default options and N-Quads output.

Every engine process runs in a memory-capped scope (harness.sandbox), with
the same time limit (TIMEOUT_S) per process.

Statuses:
    PASS   output isomorphic to the expected output, as an RDF dataset (the
           default graph and every named graph; RDF-star quoted triples
           included), and every expected target file (RML-IO dumpN.*)
           written and isomorphic — or, for a case that expects an error,
           an error was raised;
    FAIL   output differs, a target is missing, or no error was raised where one
           is expected; also a feature the engine or the translator does not
           support. An error raised where none is expected fails only if the
           output is not the expected one (the lenient rule, LENIENT in the
           detail of a pass: the output alone counts);
    N/A    hand mode only: an invalid-mapping case (no mapping to write a
           query for, see INVALID), or a module suite, for which there are
           no hand-written queries;
    TODO   no hand-written query yet.

An error is raised when the process exits with a non-zero code, times out,
is killed at the memory cap, or logs an error (an ERROR or FATAL line, a Java
exception, a Python traceback): the same rule for every engine. A case that
expects an error and gets none fails, its detail saying whether the output
was empty.

A GENERATE query is run with N-Triples output, or N-Quads when its template
has GRAPH blocks (named graphs: SPARQL-Generate 2.4.0 and later; the
translator writes them for the graph maps of the mapping).

Writes results/conformance.csv (one row per suite, case, mode, engine) and
keeps every intermediate file under results/raw/conformance/ (not versioned;
KGC_BENCH_CONFORMANCE_WORK for another directory).
"""

import argparse
import concurrent.futures as cf
import csv
import os
import re
import shutil
import sys

from harness import ENGINES, HAND, RESULTS, RML2SG, ROOT, SUITES, VERSIONS, java
from harness import rdfcompare, rmlengines, sandbox, sg

SG_ENGINES = ("sg-java", "sg-java-2.1.0", "pysparql-generate")
RML_ENGINES = ("rpt", "morph-kgc", "rmlmapper", "sdm-rdfizer") + rmlengines.NEW_RML_ENGINES
MODES = {"hand": SG_ENGINES, "translated": SG_ENGINES, "rml": RML_ENGINES}

# the KG-Construct CG modules: metadata.csv without data format nor base IRI,
# expected outputs default.nq / output.nq / output.nt, and RML-IO targets
MODULE_SUITES = ("rml-io", "rml-fnml", "rml-cc", "rml-star", "rml-lv")

RAW = os.environ.get("KGC_BENCH_CONFORMANCE_WORK") or os.path.join(RESULTS, "raw", "conformance")
TRANSLATOR = "rml2sparql-generate.rqg"
# the description of the RML-IO logical targets (format, compression, encoding
# of each file), for --targets: a second query of the translator, if it has one
TARGETS = "rml2targets.rqg"
TIMEOUT_S = 120   # per process (a translation, a run)

# Base IRI used to resolve relative IRIs, per suite: the old suite's mappings
# all declare @base <http://example.com/base/>; rml-core gives it in its
# metadata (base_iri column).
DEFAULT_BASE = {"rml-test-cases": "http://example.com/base/",
                "rml-core": "http://example.com/", "kgc-bench-extra": "http://example.com/"}
# the modules give no base IRI: the @base of the mapping, else the base their expected
# outputs use (rml-cc: http://example.com/base/, as the old suite), else rml-core's
MODULE_BASE = "http://example.com/"
MODULE_DEFAULT_BASE = {"rml-cc": "http://example.com/base/"}

# data formats of the modules' metadata (input_format1)
_MIME = {"application/json": "JSON", "text/csv": "CSV", "text/xml": "XML",
         "application/n-triples": "NT", "application/gzip+json": "JSON",
         "application/targz+json": "JSON", "application/tarxz+json": "JSON", "": "-"}

# files of a case directory that are not inputs: the mapping, its
# description, the expected outputs (main output, RML-IO target dumps)
_MAIN_EXPECTED = ("output.nq", "default.nq", "output.nt")
_NOT_INPUT = re.compile(r"^(mapping\.ttl|README\.md|output\.nq|default\.nq|output\.nt|dump\d+\..*)$")

# Invalid-mapping cases have no hand-written counterpart: a query is not a
# mapping, so "a TriplesMap without subject map" cannot even be written.
INVALID = {
    "0002c": "undefined reference: the hand-written query would refer to a column that does not exist",
    "0002e": "undefined rr:tableName / rml:path: nothing to write a query for",
    "0002g": "invalid JSONPath: nothing to write a query for",
    "0004b": "literal subject: inexpressible in a GENERATE template",
    "0007h": "non-IRI graph name: inexpressible",
    "0012c": "TriplesMap without subjectMap: impossible by construction",
    "0012d": "TriplesMap with two subjectMaps: impossible by construction",
    "0015b": "invalid language tag in the mapping: a typo in a query literal",
    "0019b": "data error expected",
    "0023a": "invalid IRI template", "0023b": "invalid IRI template",
    "0023c": "invalid IRI template", "0023d": "invalid IRI template",
    "0023e": "invalid IRI template",
    "0024a": "constant term map with an incompatible term type",
    "0025b": "wrong reference into an array",
}


def cases(suite, formats=None):
    """[(case id, data format, expects error, base IRI)]. formats: the data
    formats to keep (default: CSV, JSON, XML for rml-test-cases, whose other
    tracks need databases; every case of the other suites)."""
    d = SUITES[suite]
    out = []
    if suite == "rml-test-cases":
        formats = formats or {"CSV", "JSON", "XML"}
        meta = os.path.join(os.path.dirname(d), "metadata.csv")
        for r in csv.DictReader(open(meta, newline="", encoding="utf-8")):
            if r["data format"] in formats:
                out.append((r["RML id"], r["data format"],
                            r["error expected?"].strip() == "true",
                            DEFAULT_BASE[suite]))
    elif suite in MODULE_SUITES:
        meta = os.path.join(d, "metadata.csv")
        for r in csv.DictReader(open(meta, newline="", encoding="utf-8")):
            fmt = _MIME.get(r["input_format1"].strip(), r["input_format1"].strip())
            if formats and fmt not in formats:
                continue
            out.append((r["ID"], fmt, r["error"].strip() == "true",
                        mapping_base(os.path.join(d, r["ID"], "mapping.ttl"), suite)))
    else:
        meta = os.path.join(d, "metadata.csv")
        for r in csv.DictReader(open(meta, newline="", encoding="utf-8")):
            fmt = r["ID"].rsplit("-", 1)[1]
            if not formats or fmt in formats:
                out.append((r["ID"], fmt, r["error"].strip() == "true",
                            r["base_iri"] or DEFAULT_BASE[suite]))
    return out


def mapping_base(mapping, suite=None):
    """The base IRI for a module case: the mapping's @base, else the suite's
    default (MODULE_DEFAULT_BASE), else MODULE_BASE."""
    try:
        m = re.search(r"^\s*@base\s+<([^>]*)>", open(mapping, encoding="utf-8").read(), re.M)
    except OSError:
        m = None
    return m.group(1) if m else MODULE_DEFAULT_BASE.get(suite, MODULE_BASE)


def prepare_inputs(case_dir, work):
    """Copy the case's input documents: not its mapping, its README, nor its
    expected outputs (an engine must write them, not find them)."""
    os.makedirs(work, exist_ok=True)
    for f in os.listdir(case_dir):
        if not _NOT_INPUT.match(f) and os.path.isfile(os.path.join(case_dir, f)):
            shutil.copy(os.path.join(case_dir, f), work)
            if f.endswith(".csv"):
                _strip_caption(os.path.join(work, f))


# rml-star's two-source cases (RMLSTARTC001b to 008b): data2.csv starts with a
# Markdown caption, "**Input 1**", before its header, so that no engine can read
# its columns. The caption is removed for every engine alike.
_CAPTION = re.compile(r"^\*\*Input \d+\*\*\s*$")


def _strip_caption(path):
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        lines = f.readlines()
    if lines and _CAPTION.match(lines[0]):
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.writelines(lines[1:])


def expected_outputs(case_dir):
    """(the expected main output or None, [expected target files]): the
    target files (RML-IO dumpN.*) are written by the engine under the same
    name, in its working directory (rml:CurrentWorkingDirectory)."""
    main = next((os.path.join(case_dir, f) for f in _MAIN_EXPECTED
                 if os.path.exists(os.path.join(case_dir, f))), None)
    targets = sorted(f for f in os.listdir(case_dir) if re.match(r"^dump\d+\.", f))
    return main, targets


def judge(case_dir, work, output, deskolemize=False):
    """(status, detail) of an output (and of the target files in work)
    against the case's expected outputs."""
    expected_main, targets = expected_outputs(case_dir)
    pairs = [(output, expected_main or "", "output")] + [
        (os.path.join(work, t), os.path.join(case_dir, t), "target " + t) for t in targets]
    for got_path, exp_path, what in pairs:
        if what != "output" and not os.path.exists(got_path):
            return "FAIL", "%s not written" % what
        if what != "output" and not got_path.endswith(rdfcompare.COMPRESSIONS) and \
                rdfcompare.encoding(got_path) != rdfcompare.encoding(exp_path):
            return "FAIL", "%s: written in %s, expected %s" % (
                what, rdfcompare.encoding(got_path).upper(), rdfcompare.encoding(exp_path).upper())
        try:
            got = rdfcompare.load_dataset(got_path, "nquads" if what == "output" else None)
        except Exception as e:
            return "FAIL", "%s does not parse: %s" % (what, str(e)[:200])
        if deskolemize:
            # Skolem IRIs back to blank nodes, for a translation that writes
            # Skolem IRIs; rml2sparql-generate now writes fun:bnode blank nodes
            got = rdfcompare.deskolemize(got)
        expected = rdfcompare.load_dataset(exp_path) if exp_path else \
            rdfcompare.Dataset(default_union=False)
        ok, detail = rdfcompare.datasets_isomorphic(got, expected)
        if not ok:
            return "FAIL", detail if what == "output" else "%s: %s" % (what, detail)
    return "PASS", ""


def install_translator(work, src=None):
    """Copy the translator (entry query, templates/, iterators/) into a
    working directory: its named templates are files resolved against -b.
    src: another copy of the translator (default: the pinned one, RML2SG)."""
    src = src or RML2SG
    shutil.copy(os.path.join(src, TRANSLATOR), work)
    if os.path.exists(os.path.join(src, TARGETS)):
        shutil.copy(os.path.join(src, TARGETS), work)
    for d in ("templates", "iterators"):
        shutil.copytree(os.path.join(src, d), os.path.join(work, d),
                        dirs_exist_ok=True)


def translate(engine, mapping, work, base):
    """Run rml2sparql-generate on a mapping; return (generated query text or
    None, error)."""
    os.makedirs(os.path.join(work, "dataset"), exist_ok=True)
    shutil.copy(mapping, os.path.join(work, "dataset", "default.ttl"))
    install_translator(work)
    r = sg.run(engine, work, TRANSLATOR, "generated.rqg", base=base, timeout=120)
    if not r["ok"]:
        return None, "translation failed: " + r["error"]
    text = open(r["output"], encoding="utf-8").read()
    if "#ERROR" in text:
        line = [l for l in text.splitlines() if "#ERROR" in l][0]
        return None, "translator reports: " + line.split("#ERROR", 1)[1].strip(" :")
    # RML-IO logical targets: their description, work/targets.json
    if os.path.exists(os.path.join(work, TARGETS)) and \
            "logicalTarget" in open(mapping, encoding="utf-8").read():
        r = sg.run(engine, work, TARGETS, "targets.json", base=base, timeout=120)
        if not r["ok"]:
            return None, "translation of the targets failed: " + r["error"]
    return text, ""


def graphs_to_files(engine, work):
    """The CLI options that write the named graphs of the RML-IO logical
    targets to their files (SPARQL-Generate 2.6.0 and later, pysparql-generate 0.3.0
    and later: the same options): --graphs-to-files, and --targets with the
    description of the translator, copied to work."""
    if engine.startswith("sg-java"):
        if sg.version_tuple(engine) < (2, 6, 0):
            return []
    elif engine != "pysparql-generate" or not sg.pysg_has_option("--graphs-to-files"):
        return []
    targets = os.path.join(work, "translation", "targets.json")
    if os.path.exists(targets):
        shutil.copy(targets, os.path.join(work, "targets.json"))
        # pysparql-generate resolves --targets against its current directory
        return ["--targets", "targets.json" if engine.startswith("sg-java")
                else os.path.join(work, "targets.json")]
    return ["--graphs-to-files"]


def run_case(suite, case, fmt, expects_error, base, mode, engine):
    case_dir = os.path.join(SUITES[suite], case)
    work = os.path.join(RAW, engine, mode, suite, case)
    shutil.rmtree(work, ignore_errors=True)
    if mode == "rml":
        return run_rml_engine(engine, case_dir, work, expects_error, base)
    if mode == "hand":
        q = os.path.join(HAND, suite, case + ".rqg")
        if suite in MODULE_SUITES and not os.path.exists(q):
            return "N/A", "no hand-written query"
        if expects_error:
            num = case[5:10]
            return "N/A", INVALID.get(num, "invalid mapping: no query to write")
        if not os.path.exists(q):
            return "TODO", ""
        prepare_inputs(case_dir, work)
        shutil.copy(q, os.path.join(work, "query.rqg"))
    else:
        # the translator is run by the Java engine when the engine under test
        # cannot run it (pysparql-generate: no nested TEMPLATE)
        tengine = "sg-java" if engine == "pysparql-generate" else engine
        text, err = translate(tengine, os.path.join(case_dir, "mapping.ttl"),
                              os.path.join(work, "translation"), base)
        if text is None:
            return ("PASS", "error raised: " + err) if expects_error else ("FAIL", err)
        prepare_inputs(case_dir, work)
        with open(os.path.join(work, "query.rqg"), "w", encoding="utf-8") as f:
            f.write(text)
    # a case that expects an error: a missing document is one (RML 0002e);
    # the engine's default, a warning, suits the other cases
    extra = list(sg.fail_on_missing(engine)) if expects_error else []
    if mode == "translated":
        # RML-IO targets: the named graphs of their files, written to them
        extra += graphs_to_files(engine, work)
    r = sg.run(engine, work, "query.rqg", "output.nq", base=base,
               fmt=_format_for(os.path.join(work, "query.rqg")), timeout=TIMEOUT_S,
               extra=extra)
    if not r["ok"]:
        if expects_error:
            return "PASS", "error raised: " + r["error"]
        return lenient(case_dir, work, r["output"], r["error"], deskolemize=(mode == "translated"))
    if expects_error:
        return "FAIL", "no error raised" + _empty(r["output"])
    return judge(case_dir, work, r["output"], deskolemize=(mode == "translated"))


LENIENT = "error raised, output correct: "


def lenient(case_dir, work, output, error, deskolemize=False):
    """The lenient rule, for a case that expects no error: the output alone counts.
    An engine that raised an error (non-zero exit code, an error in its log) passes
    if the output it wrote is the expected one; not when it was killed (time, memory
    limit: no output is kept) nor when it wrote no output file."""
    if not output or not os.path.exists(output) or error.startswith(("timeout", "killed at")):
        return "FAIL", error
    status, detail = judge(case_dir, work, output, deskolemize)
    if status == "PASS":
        return "PASS", LENIENT + error
    return "FAIL", error


def _empty(path):
    """' (empty output)' when an output is missing or holds no statement."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            if any(l.strip() and not l.lstrip().startswith("#") for l in f):
                return ""
    except (OSError, TypeError):
        pass
    return " (empty output)"


# an error in an engine's log: an ERROR or FATAL line (log4j, logback, Python
# logging), a Java exception, a Python traceback
_RML_ERROR = re.compile(r"(^|\s|\[)(ERROR|FATAL|CRITICAL)(\]|\s|:)|Exception in thread|^Caused by:"
                        r"|^Traceback \(most recent call last\)", re.M)

OUTPUT = "engine-output.nq"   # the main output of an RML engine, in its directory


# The documented option of an RML engine that turns what it would skip into an
# error, given on the cases that expect an error only, as --fail-on-missing is
# given to SPARQL-Generate (harness.sg.fail_on_missing): RMLMapper's --strict
# ("the mapper will fail on invalid IRIs instead of skipping them"; its own
# test suite runs the error cases RMLTC0019b and RMLTC0023a-f in strict mode,
# src/test/java/be/ugent/rml/MapperNewRMLCoreJSONTest.java).
STRICT = {"rmlmapper": ["--strict"]}


def rml_steps(engine, work, base, expects_error=False):
    """The processes that run an RML engine on work/mapping.ttl, from work:
    [(command, file for its standard output or None)], and the path of the
    main output. Each engine as a user runs it: default options, N-Quads
    output (named graphs), the base IRI when the engine takes one; the
    configuration files are those of the performance harness
    (harness.engines), with paths in the working directory."""
    out = os.path.join(work, OUTPUT)
    if engine == "rpt":
        jar = os.path.join(ENGINES, "rpt-%s.jar" % VERSIONS["RPT_VERSION"])
        return [([java(), "-jar", jar, "rmltk", "rml", "to", "sparql", "mapping.ttl"], "queries.rq"),
                ([java(), "-jar", jar, "integrate", "queries.rq", "--out-format", "nq"], OUTPUT)], out
    if engine == "rmlmapper":
        jar = os.path.join(ENGINES, "rmlmapper-%s.jar" % VERSIONS["RMLMAPPER_VERSION"])
        return [([java(), "-jar", jar, "-m", "mapping.ttl", "-o", OUTPUT, "-s", "nquads",
                  "-b", base] + (STRICT["rmlmapper"] if expects_error else []), None)], out
    if engine == "morph-kgc":
        with open(os.path.join(work, "config.ini"), "w", encoding="utf-8") as f:
            f.write("[CONFIGURATION]\noutput_file=%s\noutput_format=N-QUADS\n\n"
                    "[DataSource1]\nmappings=%s\n" % (out, os.path.join(work, "mapping.ttl")))
        return [([sys.executable, "-m", "morph_kgc", "config.ini"], None)], out
    if engine == "sdm-rdfizer":
        # its output folder apart: it names the output file itself (.nt, or .nq
        # with graph maps)
        # new_formulation: yes, for a mapping in the namespace of the W3C CG
        # (http://w3id.org/rml/), which it reads only so (an undocumented option
        # of its configuration file; without it, no triples map is found)
        sdm = os.path.join(work, "sdm-output")
        os.makedirs(sdm, exist_ok=True)
        with open(os.path.join(work, "config.ini"), "w", encoding="utf-8") as f:
            f.write("[default]\nmain_directory: %s\n\n[datasets]\nnumber_of_datasets: 1\n"
                    "output_folder: %s\nall_in_one_file: no\nremove_duplicate: yes\n"
                    "enrichment: yes\nname: out\nordered: no\nlarge_file: false\n"
                    "new_formulation: %s\n\n"
                    "[dataset1]\nname: out\nmapping: %s\n"
                    % (work, sdm, "yes" if new_rml(os.path.join(work, "mapping.ttl")) else "no",
                       os.path.join(work, "mapping.ttl")))
        return [([sys.executable, "-m", "rdfizer", "-c", "config.ini"], None)], sdm
    if engine == "rmlstreamer":
        # part files in a directory, merged into OUTPUT by run_rml_engine
        return [(rmlengines.command(engine, "mapping.ttl", "rmlstreamer-parts", base), None)], \
            os.path.join(work, "rmlstreamer-parts")
    if engine in rmlengines.NEW_RML_ENGINES:
        # RocketRML takes no base IRI (that of the mapping); FlexRML before 3.0
        # creates the directory of its output and fails on a bare file name
        # ("cannot create directories: Invalid argument"): ./ before it
        return [(rmlengines.command(engine, "mapping.ttl",
                                    "./" + OUTPUT if engine == "flexrml" else OUTPUT,
                                    None if engine == "rocketrml" else base), None)], out
    raise ValueError("unknown RML engine %s" % engine)


def new_rml(mapping):
    """Whether a mapping is written in the namespace of the W3C KG-Construct CG
    (http://w3id.org/rml/), not in the legacy RML namespace."""
    try:
        return "<http://w3id.org/rml/>" in open(mapping, encoding="utf-8").read()
    except OSError:
        return False


def _sdm_output(sdm):
    """The output file SDM-RDFizer wrote in its folder (out.nt or out.nq),
    or None."""
    files = sorted(f for f in os.listdir(sdm) if os.path.isfile(os.path.join(sdm, f)))
    return os.path.join(sdm, files[0]) if files else None


# Diagnostic runs (never the published results), KGC_BENCH_DIAGNOSTIC: a
# comma-separated list of rewritings that tell a defect of an engine from the
# rest of what it does, on the inputs of every case alike:
#   literal-sources   the structured sources of the CG (rml:source [ a
#                     rml:RelativePathSource ; rml:path "x" ], rml:FilePath)
#                     rewritten as the path literal "x", as the copy of the
#                     RML-Core tests in the Morph-KGC repository does;
#   rpt-iri-sources   the blank nodes of the queries that "rpt rmltk rml to
#                     sparql" writes turned into IRIs before "rpt integrate"
#                     reads them back: parsed again, a blank node of the
#                     SERVICE pattern becomes a variable and its
#                     RelativePathSource is lost ("Unsupported logical source").
DIAGNOSTIC = tuple(d for d in os.environ.get("KGC_BENCH_DIAGNOSTIC", "").split(",") if d)


def literal_sources(path):
    """Rewrite, in the mapping at path, every structured source with an
    rml:path (RelativePathSource, FilePath) as the literal of its path. Returns
    the number of sources rewritten."""
    import rdflib
    RML = rdflib.Namespace("http://w3id.org/rml/")
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    n = 0
    for ls, src in list(g.subject_objects(RML.source)):
        p = g.value(src, RML.path)
        if isinstance(src, rdflib.BNode) and p is not None:
            g.remove((ls, RML.source, src))
            for t in list(g.triples((src, None, None))):
                g.remove(t)
            g.add((ls, RML.source, rdflib.Literal(str(p))))
            n += 1
    if n:
        g.serialize(path, format="turtle")
    return n


_SOURCE_BNODE = re.compile(r"_:([A-Za-z0-9_]+)\s+a\s+<http://w3id\.org/rml/(?:RelativePathSource|FilePath)>")


def iri_sources(path):
    """Turn the blank nodes of a SPARQL file that are typed as sources of the CG
    (rml:RelativePathSource, rml:FilePath) into IRIs (urn:x-bnode:<label>); the
    other blank nodes (of CONSTRUCT templates) are kept. Returns their number."""
    text = open(path, encoding="utf-8").read()
    labels = set(_SOURCE_BNODE.findall(text))
    for label in labels:
        text = re.sub(r"_:%s(?![A-Za-z0-9_])" % re.escape(label), "<urn:x-bnode:%s>" % label, text)
    open(path, "w", encoding="utf-8").write(text)
    return len(labels)


def run_rml_engine(engine, case_dir, work, expects_error, base="http://example.com/"):
    """An RML engine on the case's mapping, run in the directory of its sources."""
    prepare_inputs(case_dir, work)
    shutil.copy(os.path.join(case_dir, "mapping.ttl"), work)
    if "literal-sources" in DIAGNOSTIC:
        literal_sources(os.path.join(work, "mapping.ttl"))
    steps, out = rml_steps(engine, work, base, expects_error)
    for cmd, stdout in steps:
        if stdout:
            with open(os.path.join(work, stdout), "w", encoding="utf-8") as f:
                r = sandbox.run(cmd, TIMEOUT_S, cwd=work, stdout=f)
            if stdout == "queries.rq" and "rpt-iri-sources" in DIAGNOSTIC:
                iri_sources(os.path.join(work, stdout))
        else:
            r = sandbox.run(cmd, TIMEOUT_S, cwd=work)
        error = rml_error(r)
        if error:
            if expects_error:
                return "PASS", "error raised: " + error
            break
    if engine == "sdm-rdfizer":
        out = _sdm_output(out)
    if engine == "rmlstreamer":
        out = rmlengines.merge_parts(out, os.path.join(work, OUTPUT))
    if error:
        # the lenient rule; a failed intermediate step (RPT's translation) leaves no output
        last = (cmd, stdout) == steps[-1]
        return lenient(case_dir, work, out if last else None, error)
    if expects_error:
        return "FAIL", "no error raised" + _empty(out)
    return judge(case_dir, work, out or os.path.join(work, OUTPUT))


def rml_error(r):
    """The error an engine process raised (harness.sandbox.run result), as one
    line, or '' when it raised none."""
    log = r["stderr"] + "\n" + r["stdout"]
    m = _RML_ERROR.search(log)
    if r["status"] == "ok" and not m:
        return ""
    if r["status"] == "timeout":
        return "timeout (%ds)" % TIMEOUT_S
    if r["status"] == "oom":
        return "killed at the memory cap (%s)" % r["mem_cap"]
    if m:
        line = (log[m.start():].strip().splitlines() or [""])[0]
        if line.startswith("Traceback"):
            # the exception itself: the last line of the traceback
            tb = log[m.start():].strip().splitlines()
            line = next((l for l in reversed(tb) if l.strip() and not l.startswith(" ")), line)
    else:
        line = "%s (exit code %s): %s" % (r["status"], r["returncode"],
                                          r["stderr"].strip()[-200:])
    return sg._clean(line)


def engine_version(engine):
    if engine.startswith("sg-java"):
        return sg.jar_label(engine)
    if engine == "pysparql-generate":
        from harness.engines import pysg_version
        return pysg_version()
    if engine == "rpt":
        return "RPT " + VERSIONS.get("RPT_VERSION", "")
    if engine == "rmlmapper":
        return "RMLMapper " + VERSIONS.get("RMLMAPPER_VERSION", "")
    if engine in rmlengines.NEW_RML_ENGINES:
        return rmlengines.LABEL[engine] + " " + rmlengines.version(engine)
    if engine in ("morph-kgc", "sdm-rdfizer"):
        # the version installed (and run), pinned in requirements.txt
        from importlib import metadata
        pkg = {"morph-kgc": "morph-kgc", "sdm-rdfizer": "rdfizer"}[engine]
        try:
            v = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            v = "not installed"
        return {"morph-kgc": "Morph-KGC", "sdm-rdfizer": "SDM-RDFizer"}[engine] + " " + v
    return ""


def _format_for(query_path):
    """GENERATE queries are asked for N-Triples, or N-Quads when they have
    GRAPH blocks (sg.output_format); TEMPLATE queries write their own text
    (here, N-Quads) and refuse an output format."""
    text = open(query_path, encoding="utf-8").read()
    for line in text.splitlines():
        s = line.strip().upper()
        if s.startswith("GENERATE"):
            return sg.output_format(text)
        if s.startswith("TEMPLATE"):
            return None
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--suites", nargs="*", default=[s for s in SUITES if s != "kgc-bench-extra"],
                    help="default: the official suites; also kgc-bench-extra")
    ap.add_argument("--modes", nargs="*", default=list(MODES))
    ap.add_argument("--engines", nargs="*", default=["sg-java", "sg-java-2.1.0"])
    ap.add_argument("--mem-cap", help="memory cap of every engine process: default "
                    "KGC_BENCH_MEM_CAP, else %s; also the cap of all of them together "
                    "(KGC_BENCH_MEM_TOTAL)" % sandbox.DEFAULT_CAP)
    ap.add_argument("--formats", nargs="*",
                    help="data formats to keep (default: CSV JSON XML for rml-test-cases, "
                    "every case of the other suites)")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=2,
                    help="cases run at once (default 2: at most two JVMs at a time)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-write", action="store_true",
                    help="do not update results/conformance.csv")
    ap.add_argument("--update", action="store_true",
                    help="with --only: replace the rows of these cases in results/conformance.csv "
                    "(by default --only writes nothing)")
    args = ap.parse_args(argv)
    if args.mem_cap:
        os.environ["KGC_BENCH_MEM_CAP"] = args.mem_cap
    if sandbox.resolve():
        sandbox.setup(sandbox.resolve())
    versions = {e: engine_version(e) + ("".join(" [diagnostic: %s]" % d for d in DIAGNOSTIC)
                                         if e in RML_ENGINES else "") for e in args.engines}

    todo = []
    for suite in args.suites:
        for case, fmt, err, base in cases(suite, set(args.formats or ())):
            if args.only and case not in args.only:
                continue
            for mode in args.modes:
                for engine in args.engines:
                    if engine in MODES[mode]:
                        todo.append((suite, case, fmt, err, base, mode, engine))
    rows = []
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        futs = {ex.submit(run_case, *t): t for t in todo}
        for fu in cf.as_completed(futs):
            suite, case, fmt, err, base, mode, engine = futs[fu]
            try:
                status, detail = fu.result()
            except Exception as e:  # a harness bug must not hide the others
                status, detail = "FAIL", "harness: %s: %s" % (type(e).__name__, e)
            rows.append({"suite": suite, "case": case, "format": fmt,
                         "error_expected": err, "mode": mode, "engine": engine,
                         "version": versions[engine],
                         "status": status, "detail": _scrub(detail).replace("\n", " ")})
            if not args.quiet or status == "FAIL":
                print("%-15s %-16s %-10s %-16s %-4s %s" % (
                    suite, case, mode, engine, status, detail[:110]), flush=True)
    rows.sort(key=lambda r: (r["suite"], r["case"], r["mode"], r["engine"]))
    summary = summarise(rows)
    for line in summary:
        print(line)
    if not args.no_write and (not args.only or args.update):
        write(rows, per_case=bool(args.only))
    return 0


def _scrub(text):
    """No local path in a published detail: the repository as '.', the home as '~'."""
    for path, short in ((RAW, "<work>"), (os.path.realpath(ROOT), "."), (ROOT, "."),
                        (os.path.expanduser("~"), "~")):
        text = text.replace(path, short)
    return text


def empty_is_error(row):
    """The status under the variant "an empty output is an error raised", for the
    cases that expect an error: an engine that raised no error but wrote an empty
    output (or none) passes (SDM-RDFizer creates its output file first and stops at
    the error it detects, SDM-TIB/SDM-RDFizer#128). Other cases: the status. Not the
    published count: a column beside it (status_empty_is_error)."""
    if str(row.get("error_expected")) == "True" and row.get("status") == "FAIL" and \
            (row.get("detail") or "").startswith("no error raised (empty output)"):
        return "PASS"
    return row.get("status", "")


def summarise(rows):
    from collections import Counter
    c = Counter((r["suite"], r["format"], r["mode"], r["engine"], r["status"])
                for r in rows)
    keys = sorted({k[:4] for k in c})
    out = ["", "%-15s %-5s %-10s %-16s %5s %5s %5s %5s" % (
        "suite", "fmt", "mode", "engine", "PASS", "FAIL", "N/A", "TODO")]
    for k in keys:
        out.append("%-15s %-5s %-10s %-16s %5d %5d %5d %5d" % (
            k + tuple(c[k + (s,)] for s in ("PASS", "FAIL", "N/A", "TODO"))))
    return out


def write(rows, per_case=False):
    """Merge into results/conformance.csv: rows of other (suite, mode,
    engine) combinations are kept; per_case: only the rows of the same
    (suite, case, mode, engine) are replaced."""
    path = os.path.join(RESULTS, "conformance.csv")
    fields = ["suite", "case", "format", "error_expected", "mode", "engine",
              "version", "status", "detail", "status_empty_is_error"]
    keep = []
    key = (lambda r: (r["suite"], r["case"], r["mode"], r["engine"])) if per_case else \
        (lambda r: (r["suite"], r["mode"], r["engine"]))
    done = {key(r) for r in rows}
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            if key(r) not in done:
                keep.append(r)
    allrows = sorted(keep + rows, key=lambda r: (r["suite"], r["case"], r["mode"], r["engine"]))
    for r in allrows:
        r["status_empty_is_error"] = empty_is_error(r)
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)
    print("results/conformance.csv written (%d rows)" % len(allrows))


if __name__ == "__main__":
    sys.exit(main())
