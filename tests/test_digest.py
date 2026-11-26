"""Tests of the streaming fingerprint of an output (rdfcompare.digest) and of
the disk bound of harness.perf: every output fingerprinted, then deleted.

    python -m unittest discover tests
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

os.environ["KGC_BENCH_SLICE"] = "agents-kgcbenchtest.slice"
os.environ.pop("KGC_BENCH_MEM_TOTAL", None)

from harness import perf, rdfcompare  # noqa: E402

HAVE_RIOT = os.path.exists(rdfcompare.riot())
HAVE_SCOPES = shutil.which("systemd-run") is not None and subprocess.run(
    ["systemd-run", "--user", "--scope", "-q", "true"], capture_output=True).returncode == 0

NT = ('<http://ex/a> <http://ex/p> "x" .\n'
      '<http://ex/a> <http://ex/q> "\\u00e9t\\u00e9" .\n'
      '<http://ex/b> <http://ex/p> "1"^^<http://www.w3.org/2001/XMLSchema#integer> .\n')
# the same set: another order, a duplicate, xsd:string spelt out, the escape decoded
NT_OTHER = ('<http://ex/b> <http://ex/p> "1"^^<http://www.w3.org/2001/XMLSchema#integer> .\n'
            '<http://ex/a> <http://ex/q> "été" .\n'
            '<http://ex/a>   <http://ex/p>   "x"^^<http://www.w3.org/2001/XMLSchema#string> .\n'
            '<http://ex/b> <http://ex/p> "1"^^<http://www.w3.org/2001/XMLSchema#integer> .\n')
TTL = ('@prefix ex: <http://ex/> .\n'
       'ex:a ex:p "x" ; ex:q "été" .\n'
       'ex:b ex:p 1 .\n')


@unittest.skipUnless(HAVE_RIOT and HAVE_SCOPES, "no riot (engines/apache-jena) or no systemd scopes")
class Digest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def write(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_same_set_same_digest(self):
        a = rdfcompare.digest(self.write("a.nt", NT))
        b = rdfcompare.digest(self.write("b.nt", NT_OTHER))
        c = rdfcompare.digest(self.write("c.ttl", TTL), "turtle")
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["sha256"], c["sha256"])
        self.assertEqual((a["quads"], b["quads"], c["quads"]), (3, 3, 3))
        self.assertFalse(a["bnodes"])

    def test_one_more_triple_another_digest(self):
        a = rdfcompare.digest(self.write("a.nt", NT))
        b = rdfcompare.digest(self.write("b.nt", NT + '<http://ex/c> <http://ex/p> "y" .\n'))
        self.assertNotEqual(a["sha256"], b["sha256"])
        self.assertEqual(b["quads"], 4)

    def test_blank_nodes_flagged(self):
        self.assertTrue(rdfcompare.digest(self.write("a.nt", '_:x <http://ex/p> "x" .\n'))["bnodes"])
        self.assertFalse(rdfcompare.digest(self.write("b.nt", NT))["bnodes"])

    def test_invalid_output_raises(self):
        with self.assertRaises(RuntimeError):
            rdfcompare.digest(self.write("a.nt", "<http://ex/a> <http://ex/p> .\n"))


class KeepOutput(unittest.TestCase):
    def test_policy(self):
        self.assertFalse(perf.keep_output(SimpleNamespace(keep_outputs=False), {"triples": 10}))
        self.assertTrue(perf.keep_output(SimpleNamespace(keep_outputs=True), {}))


@unittest.skipUnless(HAVE_RIOT and HAVE_SCOPES and os.path.exists(rdfcompare.rdfc_command()[2]),
                     "no riot, rdf-canonize or systemd scopes")
class BlankNodes(unittest.TestCase):
    """RDFC-1.0: the fingerprint of an output with blank nodes compares."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def write(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_renamed_and_reordered_same_digest(self):
        a = rdfcompare.digest(self.write("a.nt", '_:x <http://ex/p> _:y .\n_:y <http://ex/q> "v" .\n'
                                                 '<http://ex/s> <http://ex/r> _:x .\n'))
        b = rdfcompare.digest(self.write("b.nt", '_:n1 <http://ex/q> "v" .\n'
                                                 '<http://ex/s> <http://ex/r> _:n0 .\n'
                                                 '_:n0 <http://ex/p> _:n1 .\n'))
        self.assertTrue(a["bnodes"])
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["quads"], 3)
        self.assertEqual(a["reason"], "")

    def test_one_more_triple_another_digest(self):
        t = '_:x <http://ex/p> _:y .\n_:y <http://ex/q> "v" .\n'
        a = rdfcompare.digest(self.write("a.nt", t))
        b = rdfcompare.digest(self.write("b.nt", t + '_:y <http://ex/q> "w" .\n'))
        self.assertNotEqual(a["sha256"], b["sha256"])

    def test_stream_and_rdfc_fingerprints_agree(self):
        """The stream fingerprint writes the lines RDFC-1.0 writes: control characters
        escaped as in canonical N-Quads (\\b, \\uXXXX, \\t)."""
        lit = '"a\\u0001b\\u0008c\\td"'
        plain = rdfcompare.digest(self.write("a.nt", "<http://ex/s> <http://ex/p> %s .\n" % lit))
        import hashlib
        expected = "<http://ex/s> <http://ex/p> \"a\\u0001b\\bc\\td\" .\n"
        self.assertEqual(plain["sha256"], hashlib.sha256(expected.encode()).hexdigest())

    def test_w3c_rdf_canon_cases(self):
        import hashlib
        d = os.path.join(os.path.dirname(__file__), "data", "rdf-canon")
        for f in sorted(os.listdir(d)):
            if f.endswith("-in.nq"):
                expected = open(os.path.join(d, f.replace("-in.nq", "-rdfc10.nq")), "rb").read()
                got = rdfcompare.digest(os.path.join(d, f))
                self.assertEqual(got["sha256"], hashlib.sha256(expected).hexdigest(), f)

    def test_timeout_gives_no_fingerprint(self):
        got = rdfcompare.digest(self.write("a.nt", '_:x <http://ex/p> _:y .\n'), rdfc_timeout=0.001)
        self.assertEqual(got["sha256"], "")
        self.assertTrue(got["reason"].startswith("RDFC-1.0"))


class CheckScale(unittest.TestCase):
    """Fingerprints compared with the reference's; kept outputs deleted."""

    def row(self, engine, digest, triples=3):
        return {"workload": "w", "scale": 1, "engine": engine, "status": "ok",
                "digest": digest, "triples": triples, "note": ""}

    def test_digests(self):
        rows = [self.row("morph-kgc", "abc"), self.row("flexrml", "abc"),
                self.row("burp", "abd")]
        perf.check_scale(rows, "w", 1, {}, SimpleNamespace(no_check=False, keep_outputs=False))
        self.assertEqual([r["equivalent"] for r in rows], ["reference", "yes", "no"])
        self.assertEqual(rows[2]["status"], "wrong-output")
        self.assertIn("fingerprint differs", rows[2]["note"])

    def test_no_fingerprint_counts_only(self):
        rows = [self.row("morph-kgc", "abc"), self.row("rpt", ""), self.row("sdm-rdfizer", "", 4)]
        perf.check_scale(rows, "w", 1, {}, SimpleNamespace(no_check=False, keep_outputs=False))
        self.assertEqual(rows[1]["equivalent"], "count")
        self.assertEqual(rows[2]["status"], "wrong-output")


@unittest.skipUnless(HAVE_RIOT and HAVE_SCOPES, "no riot or no systemd scopes")
class RunOneDeletes(unittest.TestCase):
    """run_one fingerprints the output of a run, then deletes it."""

    def test_output_deleted(self):
        d = tempfile.mkdtemp()
        try:
            class Eng:
                name, out_format = "fake", "nt"

                def version(self):
                    return "0"

                def prepare(self, job, work, xmx):
                    pass

                def command(self, job, work, xmx):
                    return ["sh", "-c", "printf '%s' > out.nt" % NT.replace("\\", "\\\\")]

                def output(self, work):
                    return os.path.join(work, "out.nt")

                def collect(self, work):
                    pass

                def discard(self, work):
                    pass

            class WL:
                name = "w"

                def job(self, scale, work):
                    return {}

            perf.TMP, old = d, perf.TMP
            args = SimpleNamespace(runs=2, timeout=60, xmx="1g", campaign="", keep_outputs=False,
                                   no_check=False)
            log = SimpleNamespace(writerow=lambda r: None)
            row, out = perf.run_one(WL(), 1, Eng(), args, log)
            perf.TMP = old
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["triples"], 3)
            self.assertEqual(len(row["digest"]), 64)
            self.assertIsNone(out)
            self.assertFalse(os.path.exists(os.path.join(d, "w", "1", "fake", "out.nt")))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
