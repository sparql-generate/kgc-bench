"""Tests of the output format asked of a query (harness.sg.output_format,
harness.conformance._format_for): N-Quads for a GENERATE query with GRAPH
blocks, N-Triples otherwise, none for a TEMPLATE query.

    python -m unittest discover tests
"""

import os
import tempfile
import unittest


def setUpModule():
    # imported here, not when the tests are collected: harness.sandbox reads
    # its slice from the environment at import, which tests/test_sandbox.py
    # sets first
    global conformance, sg
    from harness import conformance, sg


class OutputFormat(unittest.TestCase):

    def test_triples(self):
        self.assertEqual(sg.output_format("GENERATE { ?s ?p ?o . } WHERE { }"), "NT")

    def test_graph_blocks(self):
        for q in ("GENERATE { GRAPH <http://ex/g> { ?s ?p ?o . } } WHERE { }",
                  "GENERATE {\n  GRAPH ?g_1 { ?s ?p ?o . }\n} WHERE { }",
                  "GENERATE { graph ?{ ?x } { ?s ?p ?o } } WHERE { }"):
            self.assertEqual(sg.output_format(q), "NQUADS", q)

    def test_graph_in_comment_or_name(self):
        q = "# GRAPH <x> in a comment\nGENERATE { ?s <http://ex/GRAPH> ?o . } WHERE { }"
        self.assertEqual(sg.output_format(q), "NT")

    def test_format_for(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "q.rqg")
            for text, fmt in (("BASE <http://ex/>\nGENERATE { ?s ?p ?o . } WHERE { }", "NT"),
                              ("GENERATE {\n  GRAPH <http://ex/g> { ?s ?p ?o . }\n} WHERE { }", "NQUADS"),
                              ("TEMPLATE { \"x\" } WHERE { }", None)):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.assertEqual(conformance._format_for(path), fmt, text)


if __name__ == "__main__":
    unittest.main()
