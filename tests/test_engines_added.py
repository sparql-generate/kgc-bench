"""Tests of the engines added on 2026-11-26 (RocketRML, FlexRML, BURP,
RMLStreamer, ShExML; harness.rmlengines), of the conversion of a legacy RML
mapping to the RML of the W3C CG (BURP), of the ShExML GTFS mapping, and of the
memory measures of a multi-process engine (Morph-KGC).

    python -m unittest discover tests
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ["KGC_BENCH_SLICE"] = "agents-kgcbenchtest.slice"
os.environ.pop("KGC_BENCH_MEM_TOTAL", None)

from harness import ROOT, VERSIONS, conformance, rmlengines, sandbox  # noqa: E402
from harness import engines as E  # noqa: E402
from harness import perf, workloads  # noqa: E402

HAVE_SCOPES = shutil.which("systemd-run") is not None and subprocess.run(
    ["systemd-run", "--user", "--scope", "-q", "true"], capture_output=True).returncode == 0

LEGACY = """@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix rml: <http://semweb.mmlab.be/ns/rml#> .
@prefix ql: <http://semweb.mmlab.be/ns/ql#> .
<http://ex/tm> a rr:TriplesMap ;
  rml:logicalSource [ rml:source "/data/x.csv" ; rml:referenceFormulation ql:CSV ] ;
  rr:subjectMap [ rr:template "http://ex/{id}" ] ;
  rr:predicateObjectMap [ rr:predicate <http://ex/p> ; rr:objectMap [ rml:reference "v" ] ] ,
    [ rr:predicateMap [ rr:constant <http://ex/q> ] ;
      rr:objectMap [ rr:parentTriplesMap <http://ex/tm> ;
                     rr:joinCondition [ rr:child "id" ; rr:parent "id" ] ] ] .
"""


class Commands(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.work)

    def test_conformance_steps(self):
        for engine in rmlengines.NEW_RML_ENGINES:
            self.assertIn(engine, conformance.RML_ENGINES)
            steps, out = conformance.rml_steps(engine, self.work, "http://ex/")
            (cmd, stdout), = steps
            self.assertIn("mapping.ttl", cmd, engine)
            self.assertIsNone(stdout)
            self.assertTrue(out.startswith(self.work), engine)
            self.assertTrue(conformance.engine_version(engine).endswith(rmlengines.version(engine)))

    def test_base_iri(self):
        cmd = rmlengines.command("flexrml", "m.ttl", "o.nq", "http://ex/")
        self.assertEqual(cmd[-2:], ["-b", "http://ex/"])
        cmd = rmlengines.command("rmlstreamer", "m.ttl", "parts", "http://ex/")
        self.assertEqual(cmd[-2:], ["-i", "http://ex/"])
        self.assertIn("toFile", cmd)
        self.assertTrue(cmd[0].startswith(VERSIONS["JAVA_HOME_RMLSTREAMER"]))
        # RocketRML takes the base of the mapping
        steps, _ = conformance.rml_steps("rocketrml", self.work, "http://ex/")
        self.assertNotIn("http://ex/", steps[0][0])

    def test_heap(self):
        self.assertIn("-Xmx12g", rmlengines.command("burp", "m", "o", heap="12g"))
        self.assertIn("--max-old-space-size=12288", rmlengines.command("rocketrml", "m", "o", heap="12g"))
        self.assertIn("--max-old-space-size=12288", rmlengines.command("rocketrml", "m", "o",
                                                                       heap="12288m"))
        self.assertNotIn("-Xmx", " ".join(rmlengines.command("burp", "m", "o")))

    def test_merge_parts(self):
        parts = os.path.join(self.work, "parts")
        os.makedirs(os.path.join(parts, "sub"))
        for i, text in enumerate(["<a> <b> <c> .\n", "", "<d> <e> <f> .\n"]):
            open(os.path.join(parts, "sub" if i == 2 else "", str(i)), "w").write(text)
        out = rmlengines.merge_parts(parts, os.path.join(self.work, "out.nq"))
        self.assertEqual(sorted(open(out).read().splitlines()),
                         ["<a> <b> <c> .", "<d> <e> <f> ."])
        self.assertFalse(os.path.exists(parts))
        self.assertIsNone(rmlengines.merge_parts(parts, os.path.join(self.work, "none.nq")))

    def test_perf_engines(self):
        for name in rmlengines.NEW_RML_ENGINES + ("shexml", "morph-kgc-4p"):
            self.assertIn(name, E.BY_NAME)
            self.assertIn(name, perf.ENGINE_ORDER)
        job = workloads.ALL["gtfs"].job(1, self.work)
        self.assertTrue(job["shexml_mapping"].endswith("gtfs-csv.shexml"))
        cmd = E.BY_NAME["rmlmapper"].command(job, self.work, "12g")
        self.assertEqual(cmd[-1], "-d")

    def test_morph_kgc_processes(self):
        job = {"rml_absolute": "/m.ttl"}
        E.BY_NAME["morph-kgc-4p"].prepare(job, self.work, "12g")
        self.assertIn("number_of_processes=4\n", open(os.path.join(self.work, "config.ini")).read())
        E.BY_NAME["morph-kgc"].prepare(job, self.work, "12g")
        self.assertNotIn("number_of_processes", open(os.path.join(self.work, "config.ini")).read())


class RMLCore(unittest.TestCase):
    def test_to_rml_core(self):
        from rdflib import Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "m.ttl")
            open(src, "w").write(LEGACY)
            g = Graph().parse(workloads.to_rml_core(src, os.path.join(d, "core.ttl")))
            RML = Namespace("http://w3id.org/rml/")
            for t in g.all_nodes():
                self.assertFalse(str(t).startswith(("http://www.w3.org/ns/r2rml#",
                                                    "http://semweb.mmlab.be/")), t)
            self.assertIn((None, RML.reference, Literal("v")), g)
            self.assertIn((None, RML.referenceFormulation, RML.CSV), g)
            src_node = next(g.objects(None, RML.source))
            self.assertIn((src_node, RDF.type, RML.FilePath), g)
            self.assertIn((src_node, RML.path, Literal("/data/x.csv")), g)
            self.assertIn((src_node, RML.null, Literal("")), g)
            self.assertIn((URIRef("http://ex/tm"), RDF.type, RML.TriplesMap), g)
            self.assertEqual(len(list(g.objects(None, RML.joinCondition))), 1)
        finally:
            shutil.rmtree(d)


class ShExMLMapping(unittest.TestCase):
    def test_generated_mapping_is_current(self):
        """workloads/gtfs/gtfs-csv.shexml is what scripts/gtfs_mappings.py writes."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        try:
            import gtfs_mappings
        finally:
            sys.path.pop(0)
        from rdflib import Graph
        if not os.path.exists(gtfs_mappings.RML_MAPPING):
            self.skipTest("third_party/gtfs-bench not fetched")
        g = Graph().parse(gtfs_mappings.RML_MAPPING, format="turtle")
        recs = gtfs_mappings.rules(g)
        text = gtfs_mappings.shexml(recs)
        self.assertEqual(text, open(os.path.join(ROOT, "workloads", "gtfs", "gtfs-csv.shexml")).read())
        # 13 shapes; every join written as a reference condition
        self.assertEqual(len(recs), 13)
        self.assertFalse(any(k == "join" for r in recs for _, k, _, _ in r["poms"]))
        self.assertIn("gtfs:agency agency:[routes.agency_id]", text)
        self.assertIn("gtfs:parentStation stops:[stops.parent_station IF helper.notEmpty("
                      "stops.parent_station)]", text)

    def test_template(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gtfs_mappings", os.path.join(ROOT, "scripts", "gtfs_mappings.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual(m.parse_template("http://x/{a}-{b}"), ("http://x/", ["a", "-", "b"]))


@unittest.skipUnless(HAVE_SCOPES, "no systemd user session")
class Memory(unittest.TestCase):
    PY = sys.executable

    def test_sum_of_processes(self):
        """Two processes of 150 MB each: GNU time sees one, the scope both."""
        code = ("import os, time\nx = bytearray(150 * 2**20); x[::4096] = b'a' * len(x[::4096])\n"
                "pid = os.fork()\ny = bytearray(150 * 2**20); y[::4096] = b'a' * len(y[::4096])\n"
                "time.sleep(1.5)\nif pid: os.wait()\n")
        status, wall, rss, err, r = perf.timed([self.PY, "-c", code], 60)
        self.assertEqual(status, "ok")
        self.assertGreater(r["anon_peak_mb"], 450)
        self.assertGreater(rss, 450)

    def test_oom_kill_then_hang_is_oom(self):
        """A child killed at the cap while the parent waits until the time limit."""
        code = ("import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', "
                "\"x = bytearray(400 * 2**20); x[::4096] = b'a' * len(x[::4096])\"]).wait()\n"
                "time.sleep(300)\n")
        r = sandbox.run([self.PY, "-c", code], 5, mem_cap="128M")
        self.assertEqual(r["status"], "oom")


if __name__ == "__main__":
    unittest.main()
