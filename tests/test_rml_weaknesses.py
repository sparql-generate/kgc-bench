"""Tests of the prototype workloads of the branch rml-weaknesses: gtfs-feeds (K
feeds of one schema: the RML mapping once per feed, one SPARQL-Generate query),
nested-local (items numbered in their person only: an RML-LV mapping), gtfs-wkt
(an ordered aggregate; queries only).

    python -m unittest tests.test_rml_weaknesses
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from harness import ROOT, perf, workloads

RR = "http://www.w3.org/ns/r2rml#"
RML = "http://semweb.mmlab.be/ns/rml#"
WL = os.path.join(ROOT, "workloads")


class GTFSFeeds(unittest.TestCase):
    w = workloads.ALL["gtfs-feeds"]

    def test_registered(self):
        self.assertIn("gtfs-feeds", perf.DEFAULT_SCALES)
        self.assertEqual(self.w.feeds(3), ["f0001", "f0002", "f0003"])

    def test_mapping_once_per_feed(self):
        if not os.path.exists(self.w.mapping):
            raise unittest.SkipTest("third_party/gtfs-bench not fetched")
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
        tmp = tempfile.mkdtemp()
        try:
            one = Graph().parse(self.w.mapping, format="turtle")
            out = self.w._mapping(3, os.path.join(tmp, "m.ttl"), "/somewhere/")
            g = Graph().parse(out, format="turtle")
            tm = URIRef(RR + "TriplesMap")
            n = len(set(one.subjects(RDF.type, tm)))
            self.assertEqual(n, 13)
            self.assertEqual(len(set(g.subjects(RDF.type, tm))), 3 * n)
            self.assertEqual(len(g), 3 * len(one))
            sources = {str(o) for o in g.objects(None, URIRef(RML + "source"))}
            self.assertEqual(len(sources), 3 * 10)
            self.assertIn("/somewhere/STOP_TIMES-f0002.csv", sources)
            text = open(out, encoding="utf-8").read()
            self.assertNotIn("/madrid/", text)
            self.assertEqual(text.count("@base"), 1)        # FlexRML 3.1.0 reads the first only
            self.assertIn("http://transport.linkeddata.es/f0003/metro/stops/{stop_id}", text)
        finally:
            shutil.rmtree(tmp)

    def test_query_does_not_depend_on_the_feeds(self):
        q = open(self.w.files + ".rqg", encoding="utf-8").read()
        self.assertNotIn("madrid", q)
        self.assertNotRegex(q, r"f\d{4}")
        # every file of a feed is read at an IRI computed from the feed
        self.assertEqual(set(re.findall(r"<([A-Z_]+)-\{\?feed\}\.csv>", q)),
                         {"AGENCY", "CALENDAR", "CALENDAR_DATES", "FEED_INFO", "FREQUENCIES",
                          "ROUTES", "SHAPES", "STOPS", "STOP_TIMES", "TRIPS"})
        self.assertNotRegex(q, r"<[A-Z_]+\.csv>(?<!<FEEDS\.csv>)")

    def test_data_links_the_seed_once_per_feed(self):
        tmp = tempfile.mkdtemp()
        try:
            seed = os.path.join(tmp, "gtfs", "1")
            os.makedirs(seed)
            for f in ("STOPS.csv", "TRIPS.csv"):
                with open(os.path.join(seed, f), "w") as out:
                    out.write("id\n1\n")
            with mock.patch.object(workloads, "DATA", tmp), mock.patch.object(type(self.w), "seed", seed):
                self.assertTrue(self.w.ensure_data(2))
                d = self.w.data_dir(2)
            self.assertEqual(sorted(os.listdir(d)),
                             ["FEEDS.csv", "STOPS-f0001.csv", "STOPS-f0002.csv",
                              "TRIPS-f0001.csv", "TRIPS-f0002.csv"])
            self.assertEqual(open(os.path.join(d, "FEEDS.csv")).read(), "feed\nf0001\nf0002\n")
        finally:
            shutil.rmtree(tmp)


class NestedLocal(unittest.TestCase):
    w = workloads.ALL["nested-local"]

    def test_items_are_numbered_in_their_person(self):
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.object(workloads, "DATA", tmp):
                self.assertTrue(self.w.ensure_data(0.01))
                people = json.load(open(os.path.join(self.w.data_dir(0.01), "people.json")))["people"]
            self.assertEqual(len(people), 10)
            for p in people:
                self.assertEqual([i["n"] for i in p["items"]], [1, 2, 3])
                self.assertNotIn("id", p["items"][0])
        finally:
            shutil.rmtree(tmp)

    def test_mapping_is_a_logical_view(self):
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
        g = Graph().parse(os.path.join(WL, "nested-local", "nested-local-json.rml.ttl"), format="turtle")
        self.assertEqual(len(set(g.subjects(RDF.type, URIRef("http://w3id.org/rml/LogicalView")))), 1)
        self.assertEqual(len(set(g.subjects(RDF.type, URIRef("http://w3id.org/rml/IterableField")))), 1)


class GTFSWkt(unittest.TestCase):
    def test_queries(self):
        q = open(os.path.join(WL, "gtfs-wkt", "gtfs-wkt.rqg"), encoding="utf-8").read()
        s = open(os.path.join(WL, "gtfs-wkt", "shape-points.rqg"), encoding="utf-8").read()
        self.assertIn("GROUP BY ?shape_id", q)
        self.assertIn("iter:call-select(<shape-points.rqg>)", q)
        self.assertIn("ORDER BY ?shape_id xsd:integer(?seq)", s)


if __name__ == "__main__":
    unittest.main()
