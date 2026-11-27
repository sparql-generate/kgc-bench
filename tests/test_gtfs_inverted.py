"""Tests of the workload gtfs-inverted: GTFS-Madrid-Bench with the IRI-valued
branches of its mapping inverted (scripts/gtfs_mappings.py, harness.workloads).

    python -m unittest tests.test_gtfs_inverted
"""

import importlib.util
import os
import re
import shutil
import tempfile
import unittest

from harness import ROOT, perf, workloads

WL = os.path.join(ROOT, "workloads", "gtfs-inverted")
RR = "http://www.w3.org/ns/r2rml#"
RML = "http://semweb.mmlab.be/ns/rml#"


def gtfs_mappings():
    spec = importlib.util.spec_from_file_location(
        "gtfs_mappings", os.path.join(ROOT, "scripts", "gtfs_mappings.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Generated(unittest.TestCase):
    """The files of workloads/gtfs-inverted/ are what scripts/gtfs_mappings.py writes."""

    @classmethod
    def setUpClass(cls):
        cls.m = gtfs_mappings()
        if not os.path.exists(cls.m.RML_MAPPING):
            raise unittest.SkipTest("third_party/gtfs-bench not fetched")
        from rdflib import Graph
        cls.g = Graph().parse(cls.m.RML_MAPPING, format="turtle")

    def test_files_are_current(self):
        d = tempfile.mkdtemp()
        try:
            self.m.INVERTED_DIR = d
            self.m.write_inverted(self.g)
            for f in ("gtfs-inverted-csv.rml.ttl", "gtfs-inverted-csv.shexml",
                      "gtfs-inverted-csv.sa.sparql", "shexml-functions.java"):
                self.assertEqual(open(os.path.join(d, f)).read(),
                                 open(os.path.join(WL, f)).read(), f)
        finally:
            shutil.rmtree(d)

    def test_triples_maps(self):
        """13 triples maps of GTFS, one more per IRI-valued object map (23 of 86)."""
        from rdflib import Graph, Namespace, RDF
        R, L = Namespace(RR), Namespace(RML)
        recs, branches = self.m.invert_rml(self.g)
        self.assertEqual((len(recs), branches), (36, 23))
        h = Graph().parse(os.path.join(WL, "gtfs-inverted-csv.rml.ttl"), format="turtle")
        tms = set(h.subjects(RDF.type, R.TriplesMap))
        self.assertEqual(len(tms), 36)
        oms = {"gtfs": 0, "inverted": 0}
        for tm in tms:
            poms = list(h.objects(tm, R.predicateObjectMap))
            inv = "_inv_" in str(tm)
            for pom in poms:
                om = h.value(pom, R.objectMap)
                iri = h.value(om, R.parentTriplesMap) is not None or h.value(om, R.termType) == R.IRI
                pred = str(h.value(h.value(pom, R.predicateMap), R.constant))
                # an entity's triples map keeps its literals and rdf:type; a branch's
                # triples map writes one inverse IRI-valued triple
                self.assertEqual(iri, inv, (tm, pred))
                self.assertEqual(pred.startswith(self.m.INV), inv, (tm, pred))
                oms["inverted" if inv else "gtfs"] += 1
            if inv:
                self.assertEqual(len(poms), 1)
        self.assertEqual(oms, {"gtfs": 63, "inverted": 23})
        # 12 joins, each with the direction of the original swapped
        joins = [(tm, h.value(om, R.parentTriplesMap)) for tm in tms
                 for pom in h.objects(tm, R.predicateObjectMap)
                 for om in h.objects(pom, R.objectMap) if h.value(om, R.parentTriplesMap)]
        self.assertEqual(len(joins), 12)
        src = {str(tm): str(h.value(h.value(tm, L.logicalSource), L.source)) for tm in tms}
        self.assertEqual(src["http://example.com/stoptimes_0_inv_trip_trips_0"], "/data/TRIPS.csv")

    def test_same_style_as_gtfs(self):
        """The syntactic style of the GTFS mapping: every logical source and term map
        typed, predicate maps instead of rr:predicate (Morph-KGC's parsing time
        depends on these triples: only the direction of the branches may differ)."""
        from rdflib import Graph, Namespace, RDF
        R, L = Namespace(RR), Namespace(RML)
        h = Graph().parse(os.path.join(WL, "gtfs-inverted-csv.rml.ttl"), format="turtle")

        def style(g):
            tms = list(g.subjects(RDF.type, R.TriplesMap))
            poms = [p for tm in tms for p in g.objects(tm, R.predicateObjectMap)]
            oms = [o for p in poms for o in g.objects(p, R.objectMap)]
            return {
                "untyped logical sources": sum((g.value(tm, L.logicalSource), RDF.type, L.LogicalSource)
                                               not in g for tm in tms),
                "untyped subject maps": sum((g.value(tm, R.subjectMap), RDF.type, R.SubjectMap)
                                            not in g for tm in tms),
                "rr:predicate": sum(g.value(p, R.predicate) is not None for p in poms),
                "untyped predicate maps": sum((g.value(p, R.predicateMap), RDF.type, R.PredicateMap)
                                              not in g for p in poms),
                "untyped object maps": sum(
                    (o, RDF.type, R.RefObjectMap if g.value(o, R.parentTriplesMap) else R.ObjectMap)
                    not in g for o in oms)}
        self.assertEqual(style(h), style(self.g))
        self.assertEqual(set(style(h).values()), {0})

    def test_inverse_predicates(self):
        self.assertEqual(str(self.m.inverse("http://vocab.gtfs.org/terms#trip")),
                         "http://transport.linkeddata.es/inverse/trip")
        self.assertEqual(str(self.m.inverse("http://xmlns.com/foaf/0.1/page")),
                         "http://transport.linkeddata.es/inverse/page")

    def test_same_branches_everywhere(self):
        """The RML mapping, the hand-written query, the SPARQL Anything query and the
        ShExML mapping write the same inverse predicates, as many times."""
        def count(path):
            return sorted(re.findall(r"inv:(\w+)", re.sub(r"(?m)#.*$", "", open(path).read())))
        rml = count(os.path.join(WL, "gtfs-inverted-csv.rml.ttl"))
        self.assertEqual(len(rml), 23)
        sa = count(os.path.join(WL, "gtfs-inverted-csv.sa.sparql"))
        self.assertEqual(sa, rml)
        rqg = count(os.path.join(WL, "gtfs-inverted-csv.rqg"))
        self.assertEqual(rqg, rml)
        shexml = count(os.path.join(WL, "gtfs-inverted-csv.shexml"))
        # ShExML's rules() reads one object map per predicate-object map: the two
        # object maps of gtfs:service (services1, services2) give one shape, the same IRI
        self.assertEqual(sorted(shexml + ["service"]), rml)
        # literals stay in the entity's template
        text = open(os.path.join(WL, "gtfs-inverted-csv.rqg")).read()
        self.assertIn("?trip inv:trip <metro/stoptimes/{?trip_id}-{?stop_id}-{?arrival_time}> .", text)
        self.assertNotIn("gtfs:trip ", text)

    def test_invert_sa(self):
        text = ("# x\nPREFIX xyz: <x>\nCONSTRUCT {\n  ?a a gtfs:A ; foaf:name ?n ;\n"
                "      gtfs:trip ?t, ?u .\n  ?b gtfs:k ?c .\n}\nWHERE {\n  {}\n}\n")
        out = self.m.invert_sa(text, {"gtfs:trip", "gtfs:k"})
        self.assertIn("  ?a a gtfs:A ; foaf:name ?n .\n", out)
        self.assertIn("  ?t inv:trip ?a .\n  ?u inv:trip ?a .\n  ?c inv:k ?b .\n}\nWHERE {\n  {}\n}\n",
                      out)
        self.assertIn("PREFIX inv:", out)


class Workload(unittest.TestCase):
    def test_job(self):
        wl = workloads.ALL["gtfs-inverted"]
        self.assertEqual(wl.data_dir(1), workloads.ALL["gtfs"].data_dir(1))
        self.assertEqual(perf.DEFAULT_SCALES["gtfs-inverted"], [1, 10])
        work = tempfile.mkdtemp()
        try:
            job = wl.job(1, work)
            for k in ("sg_query", "sa_query", "shexml_mapping"):
                self.assertTrue(os.path.exists(job[k]), k)
                self.assertIn("gtfs-inverted", job[k])
            text = open(job["rml_absolute"]).read()
            self.assertIn('rml:source "%s/STOPS.csv"' % job["data"], text)
            self.assertNotIn('"/data/', open(job["rml_relative"]).read())
            # the GTFS job is unchanged
            g = workloads.ALL["gtfs"].job(1, work)
            self.assertTrue(g["sg_query"].endswith(os.path.join("gtfs", "gtfs-csv.rqg")))
        finally:
            shutil.rmtree(work)


if __name__ == "__main__":
    unittest.main()
