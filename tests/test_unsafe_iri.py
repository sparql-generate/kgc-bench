"""The judge reads an IRI with a space (rml:UnsafeIRI, RML-Core RMLTC0027b)
the same way whether the file writes it raw (the expected output, not valid
N-Quads) or escaped as \\u0020 (the N-Quads writer of Jena)."""

import os
import tempfile
import unittest

from harness import rdfcompare

RAW = "<http://example.com/Person/Emily Smith> <http://p> <http://o> .\n"
ESCAPED = "<http://example.com/Person/Emily\\u0020Smith> <http://p> <http://o> .\n"
ENCODED = "<http://example.com/Person/Emily%20Smith> <http://p> <http://o> .\n"


class UnsafeIRI(unittest.TestCase):

    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.nq")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return rdfcompare.load_dataset(path)

    def test_raw_and_escaped_are_the_same(self):
        expected = self.load(RAW)
        for text in (ESCAPED, ENCODED):
            self.assertTrue(rdfcompare.datasets_isomorphic(expected, self.load(text))[0], text)

    def test_other_iri_differs(self):
        other = "<http://example.com/Person/EmilySmith> <http://p> <http://o> .\n"
        self.assertFalse(rdfcompare.datasets_isomorphic(self.load(RAW), self.load(other))[0])


if __name__ == "__main__":
    unittest.main()
