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

    def test_invalid_output_raises(self):
        with self.assertRaises(RuntimeError):
            rdfcompare.digest(self.write("a.nt", "<http://ex/a> <http://ex/p> .\n"))


class KeepOutput(unittest.TestCase):
    def test_policy(self):
        args = SimpleNamespace(keep_outputs=False, no_check=False)
        self.assertFalse(perf.keep_output(args, {"bnodes": False, "triples": 10}))
        self.assertTrue(perf.keep_output(args, {"bnodes": True, "triples": 10}))
        self.assertFalse(perf.keep_output(args, {"bnodes": True, "triples": perf.CHECK_LIMIT + 1}))
        self.assertTrue(perf.keep_output(SimpleNamespace(keep_outputs=True, no_check=False),
                                         {"bnodes": False}))


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

    def test_blank_nodes_counts_only_and_outputs_deleted(self):
        d = tempfile.mkdtemp()
        try:
            kept = os.path.join(d, "out.nt")
            open(kept, "w").write("x")
            rows = [self.row("morph-kgc", ""), self.row("rpt", ""), self.row("sdm-rdfizer", "", 4)]
            outputs = {"rpt": (kept, "nt", False)}
            perf.check_scale(rows, "w", 1, outputs, SimpleNamespace(no_check=False, keep_outputs=False))
            self.assertEqual(rows[1]["equivalent"], "count")
            self.assertEqual(rows[2]["status"], "wrong-output")
            self.assertFalse(os.path.exists(kept))
            self.assertEqual(outputs, {})
        finally:
            shutil.rmtree(d)


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
