"""The time of the translation of a large RML mapping by rml2sparql-generate
(the translator of harness RML2SG, or RML2SG_DIR): the GTFS-Madrid-Bench
mapping once per feed, as in the workload gtfs-feeds, 77 feeds and 1 001
triples maps, translated by the Java engine within a bound, and in a time that
grows with the number of triples maps, not with its square (0.5.2 and 0.5.3
took more than 600 s for 1 300 triples maps; 0.5.4 about 80 s).

It runs the JVM for several minutes: skipped unless KGC_BENCH_SLOW_TESTS=1.

    KGC_BENCH_SLOW_TESTS=1 python -m unittest tests.test_translation_scale
"""

import os
import re
import shutil
import tempfile
import time
import unittest

# the bound of the translation of 1 001 triples maps, and the ratio of the
# times of 40 and 10 feeds (4 in linear time, 16 in quadratic time)
BOUND_S = 300
MAX_RATIO = 8


def feeds_mapping(source, k, out):
    """The mapping of GTFS-Madrid-Bench once per feed f0001 ... (its triples
    maps renamed, its files and its IRIs by feed; harness.workloads.GTFSFeeds)."""
    text = open(source, encoding="utf-8").read()
    head = "".join(l for l in text.splitlines(True) if l.startswith("@"))
    body = "".join(l for l in text.splitlines(True) if not l.startswith("@"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(head)
        for i in range(1, k + 1):
            feed = "f%04d" % i
            t = re.sub(r"<(\w+_0)>", lambda m: "<%s_%s>" % (feed, m.group(1)), body)
            t = re.sub(r'"/data/([A-Z_]+)\.csv"', lambda m: '"%s-%s.csv"' % (m.group(1), feed), t)
            f.write(t.replace("http://transport.linkeddata.es/madrid/",
                              "http://transport.linkeddata.es/%s/" % feed) + "\n")
    return out


@unittest.skipUnless(os.environ.get("KGC_BENCH_SLOW_TESTS") == "1", "slow: KGC_BENCH_SLOW_TESTS=1")
class TranslationScale(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from harness import RML2SG, ROOT, sg
        cls.sg, cls.translator = sg, RML2SG
        cls.source = os.path.join(ROOT, "third_party", "gtfs-bench", "mappings", "gtfs-csv.rml.ttl")
        if not os.path.exists(cls.source):
            raise unittest.SkipTest("third_party/gtfs-bench not fetched")
        if not os.path.exists(sg.jar_path("sg-java")):
            raise unittest.SkipTest("no SPARQL-Generate JAR")
        cls.tmp = tempfile.mkdtemp(prefix="kgc-translation-scale-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def translate(self, k):
        """Translate the mapping of k feeds; return (seconds, generated text)."""
        from harness.conformance import install_translator
        work = os.path.join(self.tmp, "k%d" % k)
        os.makedirs(os.path.join(work, "dataset"), exist_ok=True)
        feeds_mapping(self.source, k, os.path.join(work, "dataset", "default.ttl"))
        install_translator(work, self.translator)
        start = time.monotonic()
        r = self.sg.run("sg-java", work, "rml2sparql-generate.rqg", "generated.rqg",
                        base="http://transport.linkeddata.es/", timeout=2 * BOUND_S, xmx="4g")
        elapsed = time.monotonic() - start
        self.assertTrue(r["ok"], r.get("error"))
        return elapsed, open(r["output"], encoding="utf-8").read()

    def test_1001_triples_maps_in_bounded_time(self):
        elapsed, text = self.translate(77)
        self.assertLess(elapsed, BOUND_S)
        # one join sub-query per join of every feed (9 per feed; the 3 others
        # are made on the same row, rewriting R8)
        self.assertEqual(text.count(" → "), 77 * 9)

    def test_time_grows_with_the_mapping_not_its_square(self):
        t10, _ = self.translate(10)
        t40, _ = self.translate(40)
        self.assertLess(t40 / t10, MAX_RATIO, "10 feeds: %.1f s, 40 feeds: %.1f s" % (t10, t40))


if __name__ == "__main__":
    unittest.main()
