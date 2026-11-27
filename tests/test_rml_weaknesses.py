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


class GTFSFn(unittest.TestCase):
    """gtfs-fn (a function, RML-FNML) and its control gtfs-fn0 (the reference in its
    place): the same triples maps, and a variant of each mapping for Morph-KGC."""

    def test_control_is_the_mapping_without_the_function(self):
        with open(os.path.join(WL, "gtfs-fn", "gtfs-fn.rml.ttl"), encoding="utf-8") as f:
            fn = f.read()
        with open(os.path.join(WL, "gtfs-fn0", "gtfs-fn0.rml.ttl"), encoding="utf-8") as f:
            fn0 = f.read()
        self.assertEqual(fn.count("a rml:TriplesMap"), 2)
        self.assertEqual(fn0.count("a rml:TriplesMap"), 2)
        self.assertEqual(fn.count("rml:functionExecution <Upper>"), 2)
        self.assertNotIn("rml:functionExecution", fn0)
        self.assertEqual(fn0.count('rml:reference "shape_id"'), 2)

    def test_variant_for_morph_kgc(self):
        tmp = tempfile.mkdtemp()
        try:
            j = workloads.ALL["gtfs-fn"].job(1, tmp)
            with open(j["rml_literal_source"], encoding="utf-8") as f:
                lit = f.read()
            self.assertNotIn("rml:FilePath", lit)
            self.assertIn('rml:source "%s/SHAPES.csv"' % j["data"], lit)
            self.assertIn("grel:valueParameter ", lit)
            with open(j["rml_absolute"], encoding="utf-8") as f:
                self.assertIn("grel:valueParam ", f.read())
        finally:
            shutil.rmtree(tmp)


class GTFSDenorm(unittest.TestCase):
    """gtfs-denorm-kK: K terms of the trip of every stop time, one auxiliary triples
    map and one referencing object map per term in RML-Core, one look-up in the
    query."""

    def test_registered(self):
        for k in (1, 3, 6):
            self.assertIn("gtfs-denorm-k%d" % k, workloads.ALL)
            self.assertIn("gtfs-denorm-k%d" % k, perf.DEFAULT_SCALES)

    def test_mapping_adds_k_joins_on_trip_id(self):
        w = workloads.ALL["gtfs-denorm-k3"]
        if not os.path.exists(w.mapping):
            raise unittest.SkipTest("third_party/gtfs-bench not fetched")
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
        tmp = tempfile.mkdtemp()
        try:
            j = w.job(1, tmp)
            g = Graph().parse(j["rml_absolute"], format="turtle")
            one = Graph().parse(w.mapping, format="turtle")
            tm = URIRef(RR + "TriplesMap")
            self.assertEqual(len(set(g.subjects(RDF.type, tm))), 13 + 3)
            parents = set(g.objects(None, URIRef(RR + "parentTriplesMap")))
            self.assertEqual(len(parents), len(set(one.objects(None, URIRef(RR + "parentTriplesMap")))) + 3)
            st = URIRef("http://example.com/stoptimes_0")
            self.assertEqual(len(list(g.objects(st, URIRef(RR + "predicateObjectMap")))),
                             len(list(one.objects(st, URIRef(RR + "predicateObjectMap")))) + 3)
            text = open(j["rml_absolute"], encoding="utf-8").read()
            self.assertEqual(text.count("@base"), 1)
            self.assertNotIn('"/data/', text)
            rel = open(j["rml_relative"], encoding="utf-8").read()
            self.assertEqual(rel.count('rml:source "TRIPS.csv"'), 1 + 3)
        finally:
            shutil.rmtree(tmp)

    def test_query_looks_the_trip_up_once(self):
        q = workloads.ALL["gtfs-denorm-k6"].query()
        self.assertEqual(q.count("?trip key:trip ?kt"), 2)   # stop times, frequencies
        self.assertEqual(q.count("OPTIONAL { ?trip den:"), 6)
        self.assertIn('ITERATOR iter:CSV(<TRIPS.csv>, "trip_id", "route_id", "service_id", '
                      '"shape_id", "block_id", "direction_id", "wheelchair_accessible")', q)
        self.assertEqual(q.count("ex:trip"), 6)
        self.assertEqual(workloads.ALL["gtfs-denorm-k1"].query().count("ex:trip"), 1)


class GTFSFnSubject(unittest.TestCase):
    """gtfs-fn-subject: the subjects of stoptimes_0 and shapePoints_0 computed by a
    function; gtfs-fn-subject0, the same mapping with the templates."""

    def setUp(self):
        if not os.path.exists(workloads.GTFS.mapping):
            raise unittest.SkipTest("third_party/gtfs-bench not fetched")
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_function_in_two_subject_maps(self):
        j = workloads.ALL["gtfs-fn-subject"].job(1, os.path.join(self.tmp, "fn"))
        j0 = workloads.ALL["gtfs-fn-subject0"].job(1, os.path.join(self.tmp, "fn0"))
        fn = open(j["rml_absolute"], encoding="utf-8").read()
        fn0 = open(j0["rml_absolute"], encoding="utf-8").read()
        self.assertEqual(fn.count("rml:functionExecution"), 2)
        self.assertEqual(fn.count("grel:valueParam "), 2)
        self.assertNotIn("rml:functionExecution", fn0)
        self.assertIn("<http://w3id.org/rml/>", fn0)
        lit = open(j["rml_literal_source"], encoding="utf-8").read()
        self.assertNotIn("rml:FilePath", lit)
        self.assertEqual(lit.count("grel:valueParameter "), 2)
        self.assertIn('rml:source "%s/STOP_TIMES.csv"' % j["data"], lit)

    def test_variant_without_the_joins_of_these_triples_maps(self):
        from rdflib import Graph, URIRef
        j = workloads.ALL["gtfs-fn-subject-nojoin"].job(1, os.path.join(self.tmp, "nj"))
        j0 = workloads.ALL["gtfs-fn-subject0"].job(1, os.path.join(self.tmp, "fn0"))
        ptm = URIRef("http://w3id.org/rml/parentTriplesMap")
        n = len(list(Graph().parse(j["rml_absolute"], format="turtle").objects(None, ptm)))
        n0 = len(list(Graph().parse(j0["rml_absolute"], format="turtle").objects(None, ptm)))
        self.assertEqual(n0 - n, 3)
        q = workloads.ALL["gtfs-fn-subject-nojoin"].query()
        self.assertNotIn("gtfs:shapePoint", q)
        self.assertNotIn("gtfs:trip ?trip ; gtfs:stop", q)
        self.assertEqual(q.count("BIND(IRI(UCASE(CONCAT("), 2)

    def test_query_binds_the_subjects_once(self):
        q = workloads.ALL["gtfs-fn-subject"].query()
        self.assertEqual(q.count("BIND(IRI(UCASE(CONCAT("), 2)
        self.assertNotIn("<metro/stoptimes/", q)
        self.assertEqual(workloads.ALL["gtfs-fn-subject0"].query(),
                         open(workloads.GTFS.files + ".rqg", encoding="utf-8").read())


class GTFSWkt(unittest.TestCase):
    def test_queries(self):
        q = open(os.path.join(WL, "gtfs-wkt", "gtfs-wkt.rqg"), encoding="utf-8").read()
        s = open(os.path.join(WL, "gtfs-wkt", "shape-points.rqg"), encoding="utf-8").read()
        self.assertIn("GROUP BY ?shape_id", q)
        self.assertIn("iter:call-select(<shape-points.rqg>)", q)
        self.assertIn("ORDER BY ?shape_id xsd:integer(?seq)", s)


if __name__ == "__main__":
    unittest.main()
