"""Tests of the pin overrides (harness.apply_overrides: another version of an
engine measured without changing versions.env) and of the diagnostic
rewritings of harness.conformance (KGC_BENCH_DIAGNOSTIC). No engine is run.

    python -m unittest discover tests
"""

import os
import tempfile
import unittest

from harness import PIN_OVERRIDE, apply_overrides


class PinOverride(unittest.TestCase):
    def test_override_replaces_a_pin(self):
        pins = {"RPT_VERSION": "2.0.0-rc7", "BURP_VERSION": "0.1.3"}
        got = apply_overrides(pins, {PIN_OVERRIDE + "RPT_VERSION": "2.0.0-rc8", "HOME": "/h"})
        self.assertEqual(got, {"RPT_VERSION": "2.0.0-rc8", "BURP_VERSION": "0.1.3"})
        self.assertEqual(pins["RPT_VERSION"], "2.0.0-rc7")

    def test_no_override(self):
        pins = {"RPT_VERSION": "2.0.0-rc7"}
        self.assertEqual(apply_overrides(pins, {PIN_OVERRIDE: "x"}), pins)


MAPPING = """@prefix rml: <http://w3id.org/rml/> .
<http://ex/TM> a rml:TriplesMap ;
  rml:logicalSource [ rml:source [ a rml:RelativePathSource ; rml:root rml:MappingDirectory ;
      rml:path "student.csv" ] ; rml:referenceFormulation rml:CSV ] ;
  rml:subjectMap [ rml:template "http://ex/{ID}" ] .
"""

QUERY = """CONSTRUCT { _:x <http://ex/p> ?v0 . }
WHERE { SERVICE <https://w3id.org/aksw/norse#rml.source>
  { <https://w3id.org/aksw/norse#rml.source> <http://w3id.org/rml/source> _:b0 .
    _:b0 a <http://w3id.org/rml/RelativePathSource> ; <http://w3id.org/rml/path> "s.json" .
    _:b01 <http://ex/q> "kept" . } }
"""


class SuitesDirectory(unittest.TestCase):
    def test_third_party_override(self):
        # the suites of another date (scripts/suites_at.sh), read in a fresh process
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = tempfile.mkdtemp()
        out = subprocess.run([sys.executable, "-c", "from harness import SUITES; print(SUITES['rml-core'])"],
                             cwd=root, capture_output=True, text=True,
                             env=dict(os.environ, KGC_BENCH_THIRD_PARTY=d)).stdout.strip()
        self.assertEqual(out, os.path.join(d, "rml-core", "test-cases"))


class OldRmlCore(unittest.TestCase):
    def test_metadata_without_base_iri(self):
        # rml-core before 2025-08: no base_iri column, expected outputs on .../base/
        from harness import conformance
        import harness
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "RMLTC0001a-JSON"))
        open(os.path.join(d, "RMLTC0001a-JSON", "mapping.ttl"), "w").write("")
        open(os.path.join(d, "metadata.csv"), "w").write(
            "ID,title,mapping,error\nRMLTC0001a-JSON,t,mapping.ttl,false\n")
        old = harness.SUITES["rml-core"]
        conformance.SUITES["rml-core"] = d
        try:
            self.assertEqual(conformance.cases("rml-core"),
                             [("RMLTC0001a-JSON", "JSON", False, "http://example.com/base/")])
        finally:
            conformance.SUITES["rml-core"] = old


class Diagnostics(unittest.TestCase):
    def setUp(self):
        from harness import conformance
        self.c = conformance
        self.dir = tempfile.mkdtemp()

    def test_literal_sources(self):
        import rdflib
        p = os.path.join(self.dir, "mapping.ttl")
        open(p, "w").write(MAPPING)
        self.assertEqual(self.c.literal_sources(p), 1)
        g = rdflib.Graph().parse(p)
        RML = rdflib.Namespace("http://w3id.org/rml/")
        self.assertEqual([str(o) for o in g.objects(None, RML.source)], ["student.csv"])
        self.assertIsNone(g.value(None, RML.path))
        self.assertEqual(self.c.literal_sources(p), 0)
        open(p, "w").write('<http://ex/a> <http://ex/b> "bad \\q escape" .')
        self.assertEqual(self.c.literal_sources(p), 0)

    def test_iri_sources(self):
        p = os.path.join(self.dir, "queries.rq")
        open(p, "w").write(QUERY)
        self.assertEqual(self.c.iri_sources(p), 1)
        text = open(p).read()
        self.assertEqual(text.count("<urn:x-bnode:b0>"), 2)
        self.assertIn("_:x <http://ex/p>", text)
        self.assertIn("_:b01 <http://ex/q>", text)


if __name__ == "__main__":
    unittest.main()


class PatchedEngines(unittest.TestCase):
    """An engine built with proposed patches (scripts/patches/): its PYTHONPATH
    goes to the engine's processes only."""

    def test_pythonpath_of_a_patched_python_engine(self):
        from harness import conformance
        old = os.environ.get("KGC_BENCH_PYTHONPATH_MORPH_KGC")
        os.environ["KGC_BENCH_PYTHONPATH_MORPH_KGC"] = "/x/morph"
        try:
            self.assertEqual(conformance.engine_env("morph-kgc")["PYTHONPATH"], "/x/morph")
            self.assertIsNone(conformance.engine_env("sdm-rdfizer"))
            self.assertIsNone(conformance.engine_env("rmlmapper"))
        finally:
            if old is None:
                del os.environ["KGC_BENCH_PYTHONPATH_MORPH_KGC"]
            else:
                os.environ["KGC_BENCH_PYTHONPATH_MORPH_KGC"] = old

    def test_sdm_rdfizer_is_given_the_base_iri(self):
        from harness import conformance
        work = tempfile.mkdtemp()
        open(os.path.join(work, "mapping.ttl"), "w").write(MAPPING)
        conformance.rml_steps("sdm-rdfizer", work, "http://ex/")
        self.assertIn("base_iri: http://ex/\n", open(os.path.join(work, "config.ini")).read())
