"""Tests of the conformance harness for the RML engines and the RML module
suites (harness.conformance), and of the oracle's readers for their outputs
(harness.rdfcompare: RDF-star, RDF/JSON, compressed targets). No engine is
run.

    python -m unittest discover tests
"""

import gzip
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile


def setUpModule():
    # imported here, not when the tests are collected: harness.sandbox reads
    # its slice from the environment at import, which tests/test_sandbox.py
    # sets first
    global conformance, rdfcompare
    from harness import conformance, rdfcompare


NQ = ('<http://ex/a> <http://ex/p> "1" .\n'
      '<http://ex/a> <http://ex/q> <http://ex/b> <http://ex/g> .\n')


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        f.write(text)
    return path


class ModuleCase(unittest.TestCase):
    """A fake module suite: metadata.csv and one case directory per case."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.suite = os.path.join(self.tmp, "test-cases")
        write(os.path.join(self.suite, "metadata.csv"),
              "ID,title,description,specification,mapping,input_format1,error\n"
              "T1,t,d,s,mapping.ttl,application/json,false\n"
              "T2,t,d,s,mapping.ttl,text/csv,true\n"
              "T3,t,d,s,mapping.ttl,,false\n")
        write(os.path.join(self.suite, "T1", "mapping.ttl"), "@base <http://ex/base/> .\n")
        write(os.path.join(self.suite, "T2", "mapping.ttl"), "@prefix rml: <http://w3id.org/rml/> .\n")
        write(os.path.join(self.suite, "T3", "mapping.ttl"), "")
        self.saved = dict(conformance.SUITES)
        conformance.SUITES["rml-io"] = self.suite

    def tearDown(self):
        conformance.SUITES.clear()
        conformance.SUITES.update(self.saved)
        shutil.rmtree(self.tmp)

    def test_cases(self):
        self.assertEqual(conformance.cases("rml-io"), [
            ("T1", "JSON", False, "http://ex/base/"),
            ("T2", "CSV", True, conformance.MODULE_BASE),
            ("T3", "-", False, conformance.MODULE_BASE)])
        self.assertEqual([c[0] for c in conformance.cases("rml-io", {"CSV"})], ["T2"])

    def test_hand_mode_has_no_query(self):
        for case, fmt, err, base in conformance.cases("rml-io"):
            self.assertEqual(conformance.run_case("rml-io", case, fmt, err, base, "hand", "sg-java"),
                             ("N/A", "no hand-written query"))


class Inputs(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.case = os.path.join(self.tmp, "case")
        for f in ("mapping.ttl", "README.md", "default.nq", "dump1.nq", "dump2.nq.gz",
                  "Friends.json", "Friends.json.gz", "data1.csv"):
            write(os.path.join(self.case, f), "x")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_expected_outputs_are_not_inputs(self):
        work = os.path.join(self.tmp, "work")
        conformance.prepare_inputs(self.case, work)
        self.assertEqual(sorted(os.listdir(work)), ["Friends.json", "Friends.json.gz", "data1.csv"])

    def test_expected_outputs(self):
        main, targets = conformance.expected_outputs(self.case)
        self.assertEqual(os.path.basename(main), "default.nq")
        self.assertEqual(targets, ["dump1.nq", "dump2.nq.gz"])

    def test_star_output_name(self):
        os.unlink(os.path.join(self.case, "default.nq"))
        write(os.path.join(self.case, "output.nt"), "x")
        self.assertEqual(os.path.basename(conformance.expected_outputs(self.case)[0]), "output.nt")


class Judge(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.case = os.path.join(self.tmp, "case")
        self.work = os.path.join(self.tmp, "work")
        write(os.path.join(self.case, "default.nq"), NQ)
        os.makedirs(self.work)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def out(self, text=NQ):
        return write(os.path.join(self.work, conformance.OUTPUT), text)

    def test_pass(self):
        self.assertEqual(conformance.judge(self.case, self.work, self.out()), ("PASS", ""))

    def test_named_graph_differs(self):
        status, detail = conformance.judge(self.case, self.work, self.out(NQ.replace("/g>", "/h>")))
        self.assertEqual(status, "FAIL")
        self.assertIn("named graphs", detail)

    def test_missing_output_is_empty(self):
        status, _ = conformance.judge(self.case, self.work, os.path.join(self.work, "none.nq"))
        self.assertEqual(status, "FAIL")

    def test_targets(self):
        write(os.path.join(self.case, "default.nq"), "")
        with gzip.open(os.path.join(self.case, "dump1.nq.gz"), "wt") as f:
            f.write(NQ)
        out = self.out("")
        self.assertEqual(conformance.judge(self.case, self.work, out),
                         ("FAIL", "target dump1.nq.gz not written"))
        with gzip.open(os.path.join(self.work, "dump1.nq.gz"), "wt") as f:
            f.write(NQ)
        self.assertEqual(conformance.judge(self.case, self.work, out), ("PASS", ""))
        with gzip.open(os.path.join(self.work, "dump1.nq.gz"), "wt") as f:
            f.write(NQ.splitlines()[0] + "\n")
        status, detail = conformance.judge(self.case, self.work, out)
        self.assertEqual(status, "FAIL")
        self.assertTrue(detail.startswith("target dump1.nq.gz:"), detail)

    def test_utf16_target(self):
        write(os.path.join(self.case, "default.nq"), "")
        write(os.path.join(self.case, "dump1.nq"), NQ.encode("utf-16"), "wb")
        out = self.out("")
        write(os.path.join(self.work, "dump1.nq"), NQ)
        self.assertEqual(conformance.judge(self.case, self.work, out),
                         ("FAIL", "target dump1.nq: written in UTF-8, expected UTF-16"))
        write(os.path.join(self.work, "dump1.nq"), NQ.encode("utf-16"), "wb")
        self.assertEqual(conformance.judge(self.case, self.work, out), ("PASS", ""))

    def test_empty(self):
        self.assertEqual(conformance._empty(self.out("# nothing\n\n")), " (empty output)")
        self.assertEqual(conformance._empty(None), " (empty output)")
        self.assertEqual(conformance._empty(self.out()), "")


def result(status="ok", stderr="", stdout="", returncode=0):
    return {"status": status, "stderr": stderr, "stdout": stdout, "returncode": returncode,
            "mem_cap": "16G"}


class Errors(unittest.TestCase):
    """One rule for every engine: an error is an exit code, a timeout, the
    memory cap, or an error in the log."""

    def test_no_error(self):
        self.assertEqual(conformance.rml_error(result(stderr="INFO done\nWARN skipped\n")), "")

    def test_log_levels(self):
        for log in ("18:47:49.707 [main] ERROR be.ugent.rml.cli.Main - Cannot invoke x",
                    "[ERROR] [o.a.s.c.m.SparqlIntegrateCmdImpls:1027] - Error encountered",
                    "ERROR:root:bad mapping", "CRITICAL | x",
                    'Exception in thread "main" java.lang.StackOverflowError'):
            self.assertTrue(conformance.rml_error(result(stderr="INFO start\n" + log + "\n")), log)

    def test_traceback(self):
        tb = ('Traceback (most recent call last):\n  File "x.py", line 1, in <module>\n'
              '    f()\nFileNotFoundError: [Errno 2] No such file\n')
        self.assertEqual(conformance.rml_error(result("error", tb, returncode=1)),
                         "FileNotFoundError: [Errno 2] No such file")

    def test_status(self):
        self.assertIn("exit code 3", conformance.rml_error(result("error", "boom", returncode=3)))
        self.assertTrue(conformance.rml_error(result("timeout")).startswith("timeout"))
        self.assertIn("memory cap", conformance.rml_error(result("oom")))

    def test_word_error_in_data_is_not_an_error(self):
        self.assertEqual(conformance.rml_error(result(stdout="Semantifying ERRORS.csv...\n")), "")


class Steps(unittest.TestCase):
    """Every RML engine runs from its working directory, on mapping.ttl, with
    N-Quads output; configuration files hold the paths of that directory."""

    def setUp(self):
        self.work = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.work)

    def test_engines(self):
        for engine in conformance.RML_ENGINES:
            steps, out = conformance.rml_steps(engine, self.work, "http://ex/")
            self.assertTrue(out.startswith(self.work), engine)
            self.assertTrue(any("mapping.ttl" in " ".join(c) or
                                os.path.exists(os.path.join(self.work, "config.ini"))
                                for c, _ in steps), engine)
        self.assertRaises(ValueError, conformance.rml_steps, "unknown", self.work, "")

    def test_rmlmapper(self):
        (cmd, stdout), = conformance.rml_steps("rmlmapper", self.work, "http://ex/")[0]
        self.assertEqual(cmd[-6:], ["-o", conformance.OUTPUT, "-s", "nquads", "-b", "http://ex/"])
        self.assertIsNone(stdout)

    def test_morph_kgc_config(self):
        conformance.rml_steps("morph-kgc", self.work, "http://ex/")
        ini = open(os.path.join(self.work, "config.ini")).read()
        self.assertIn("output_format=N-QUADS", ini)
        self.assertIn("mappings=%s" % os.path.join(self.work, "mapping.ttl"), ini)
        self.assertIn("output_file=%s" % os.path.join(self.work, conformance.OUTPUT), ini)

    def test_sdm_rdfizer_config(self):
        _, out = conformance.rml_steps("sdm-rdfizer", self.work, "http://ex/")
        ini = open(os.path.join(self.work, "config.ini")).read()
        self.assertIn("new_formulation: no\n", ini)
        write(os.path.join(self.work, "mapping.ttl"), "@prefix rml: <http://w3id.org/rml/> .\n")
        _, out = conformance.rml_steps("sdm-rdfizer", self.work, "http://ex/")
        ini = open(os.path.join(self.work, "config.ini")).read()
        self.assertIn("new_formulation: yes\n", ini)
        self.assertIn("main_directory: %s\n" % self.work, ini)
        self.assertIn("output_folder: %s\n" % out, ini)
        self.assertIsNone(conformance._sdm_output(out))
        write(os.path.join(out, "out.nq"), NQ)
        self.assertEqual(conformance._sdm_output(out), os.path.join(out, "out.nq"))

    def test_versions(self):
        for engine in ("rmlmapper", "morph-kgc", "sdm-rdfizer"):
            self.assertTrue(conformance.engine_version(engine), engine)


class Write(unittest.TestCase):
    """--only --update replaces the rows of its cases, and keeps the others."""

    def test_per_case(self):
        tmp = tempfile.mkdtemp()
        saved = conformance.RESULTS
        conformance.RESULTS = tmp
        try:
            row = dict(suite="rml-io", case="A", format="JSON", error_expected=False,
                       mode="rml", engine="rmlmapper", version="v", status="FAIL", detail="")
            conformance.write([row, dict(row, case="B")])
            conformance.write([dict(row, status="PASS")], per_case=True)
            import csv
            got = {(r["case"], r["status"]) for r in csv.DictReader(open(os.path.join(tmp, "conformance.csv")))}
            self.assertEqual(got, {("A", "PASS"), ("B", "FAIL")})
            conformance.write([dict(row, status="PASS")])
            got = {r["case"] for r in csv.DictReader(open(os.path.join(tmp, "conformance.csv")))}
            self.assertEqual(got, {"A"})
        finally:
            conformance.RESULTS = saved
            shutil.rmtree(tmp)


class Readers(unittest.TestCase):
    """The oracle reads RDF-star, RDF/JSON and compressed outputs."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def iso(self, a, b):
        return rdfcompare.datasets_isomorphic(rdfcompare.load_dataset(a),
                                              rdfcompare.load_dataset(b))[0]

    def test_star(self):
        a = write(os.path.join(self.tmp, "a.nt"),
                  '_:x <http://ex/p> <http://ex/o> .\n'
                  '<< _:x <http://ex/p> <http://ex/o> >> <http://ex/q> "A" .\n')
        b = write(os.path.join(self.tmp, "b.nq"),
                  '_:y <http://ex/p> <http://ex/o> .\n'
                  '<< _:y <http://ex/p> <http://ex/o> >> <http://ex/q> "A" .\n')
        c = write(os.path.join(self.tmp, "c.nq"),
                  '_:y <http://ex/p> <http://ex/o> .\n'
                  '<< _:z <http://ex/p> <http://ex/o> >> <http://ex/q> "A" .\n')
        d = write(os.path.join(self.tmp, "d.nq"),
                  '_:y <http://ex/p> <http://ex/o> .\n'
                  '<< _:y <http://ex/p> <http://ex/o> >> <http://ex/q> "A" <http://ex/g> .\n')
        self.assertTrue(self.iso(a, b))
        self.assertFalse(self.iso(a, c))   # the quoted subject is another blank node
        self.assertFalse(self.iso(a, d))   # in a named graph

    def test_rdf_json(self):
        a = write(os.path.join(self.tmp, "a.rdfjson"), json.dumps({
            "http://ex/a": {"http://ex/p": [{"type": "literal", "value": "1"}],
                            "http://ex/q": [{"type": "uri", "value": "http://ex/b"},
                                            {"type": "literal", "value": "x", "lang": "en"},
                                            {"type": "bnode", "value": "_:n"}]}}))
        b = write(os.path.join(self.tmp, "b.nq"),
                  '<http://ex/a> <http://ex/p> "1" .\n<http://ex/a> <http://ex/q> <http://ex/b> .\n'
                  '<http://ex/a> <http://ex/q> "x"@en .\n<http://ex/a> <http://ex/q> _:m .\n')
        self.assertTrue(self.iso(a, b))

    def test_compressed(self):
        nq = write(os.path.join(self.tmp, "x.nq"), NQ)
        with zipfile.ZipFile(os.path.join(self.tmp, "x.nq.zip"), "w") as z:
            z.writestr("dump1.nq", NQ)
        for ext, mode in ((".tar.gz", "w:gz"), (".tar.xz", "w:xz")):
            with tarfile.open(os.path.join(self.tmp, "x.nq" + ext), mode) as t:
                data = NQ.encode()
                info = tarfile.TarInfo("dump1.nq")
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        with gzip.open(os.path.join(self.tmp, "x.nq.gz"), "wt") as f:
            f.write(NQ)
        for ext in (".gz", ".zip", ".tar.gz", ".tar.xz"):
            self.assertTrue(self.iso(os.path.join(self.tmp, "x.nq" + ext), nq), ext)
        empty = os.path.join(self.tmp, "e.nq.zip")
        with zipfile.ZipFile(empty, "w"):
            pass
        self.assertEqual(len(rdfcompare.load_dataset(empty)), 0)


if __name__ == "__main__":
    unittest.main()
