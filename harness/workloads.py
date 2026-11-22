"""The workloads of RQ3. A workload prepares, for one scale, a *job*: the
data directory, the RML mapping (with absolute paths, and with paths
relative to the data directory for rml2sparql-generate), the hand-written
SPARQL-Generate query, the SPARQL Anything query, and the base IRIs.

gtfs         GTFS-Madrid-Bench, CSV distribution, official mapping (13 triples
             maps, 9 joins); data from the benchmark's generator
             (scripts/gtfs_data.sh N)
nested-json  synthetic nested JSON: N people, each with an address object and
             3 items; two iterations ($.people[*], $.people[*].items[*]) and
             a multi-valued reference ($.items[*].type); scale = N / 1000
nested-xml   the same data and mapping in XML (attributes, nested elements)
flat-csv     synthetic flat CSV, N rows x 8 columns, one triples map, no join:
             the memory-bounded runs; scale = N / 1000
"""

import json
import os
import random

from harness import DATA, ROOT

WL = os.path.join(ROOT, "workloads")


def _rewrite(mapping, out, old, new):
    text = open(mapping, encoding="utf-8").read().replace(old, new)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return out


class Workload:
    name = ""
    sg_base = "http://example.com/base/"
    rml_base = "http://example.com/base/"

    def data_dir(self, scale):
        return os.path.join(DATA, self.name, str(scale))

    def ensure_data(self, scale):
        return os.path.isdir(self.data_dir(scale))

    def job(self, scale, work):
        raise NotImplementedError


class GTFS(Workload):
    name = "gtfs"
    sg_base = "http://transport.linkeddata.es/madrid/"
    mapping = os.path.join(ROOT, "third_party", "gtfs-bench", "mappings", "gtfs-csv.rml.ttl")

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": _rewrite(self.mapping, os.path.join(work, "mapping-abs.rml.ttl"),
                                     '"/data/', '"%s/' % d),
            "rml_relative": _rewrite(self.mapping, os.path.join(work, "mapping-rel.rml.ttl"),
                                     '"/data/', '"'),
            "sg_query": os.path.join(WL, "gtfs", "gtfs-csv.rqg"),
            "sa_query": os.path.join(WL, "gtfs", "gtfs-csv.sa.sparql"),
            "sg_base": self.sg_base, "rml_base": self.rml_base,
        }


class Nested(Workload):
    """People with nested address and items, in JSON or XML."""
    sg_base = "http://example.org/"     # the BASE of the hand-written queries

    def __init__(self, fmt):
        self.fmt = fmt
        self.name = "nested-" + fmt

    def ensure_data(self, scale):
        d = self.data_dir(scale)
        f = os.path.join(d, "people." + self.fmt)
        if os.path.exists(f):
            return True
        os.makedirs(d, exist_ok=True)
        n = int(scale * 1000)
        rnd = random.Random(42)
        cities = ["Paris", "Lyon", "Saint-Etienne", "Madrid", "Gent", "Bologna"]
        types = ["book", "pen", "cup", "lamp", "phone", "bag"]
        tmp = f + ".part"
        with open(tmp, "w", encoding="utf-8") as out:
            if self.fmt == "json":
                out.write('{"people":[\n')
            else:
                out.write('<?xml version="1.0" encoding="UTF-8"?>\n<people>\n')
            for i in range(n):
                items = [{"id": "%d-%d" % (i, k), "type": rnd.choice(types),
                          "weight": rnd.randint(1, 500)} for k in range(3)]
                p = {"id": i, "name": "person %d" % i,
                     "address": {"city": rnd.choice(cities), "zip": "%05d" % rnd.randint(0, 99999)},
                     "items": items}
                if self.fmt == "json":
                    out.write(("," if i else "") + json.dumps(p, separators=(",", ":")) + "\n")
                else:
                    out.write('<person id="%d"><name>%s</name><address><city>%s</city><zip>%s</zip></address><items>%s</items></person>\n' % (
                        i, p["name"], p["address"]["city"], p["address"]["zip"],
                        "".join('<item id="%s"><type>%s</type><weight>%d</weight></item>' % (
                            it["id"], it["type"], it["weight"]) for it in items)))
            out.write("]}\n" if self.fmt == "json" else "</people>\n")
        os.rename(tmp, f)
        return True

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        src = os.path.join(WL, "nested", "nested-%s.rml.ttl" % self.fmt)
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": _rewrite(src, os.path.join(work, "mapping-abs.rml.ttl"),
                                     '"people.', '"%s/people.' % d),
            "rml_relative": src,
            "sg_query": os.path.join(WL, "nested", "nested-%s.rqg" % self.fmt),
            "sa_query": os.path.join(WL, "nested", "nested-%s.sa.sparql" % self.fmt),
            "sg_base": self.sg_base, "rml_base": self.rml_base,
        }


class FlatCSV(Workload):
    name = "flat-csv"
    sg_base = "http://example.org/"     # the BASE of the hand-written query

    def ensure_data(self, scale):
        d = self.data_dir(scale)
        f = os.path.join(d, "rows.csv")
        if os.path.exists(f):
            return True
        os.makedirs(d, exist_ok=True)
        n = int(scale * 1000)
        rnd = random.Random(7)
        with open(f + ".part", "w", encoding="utf-8") as out:
            out.write("id,name,city,age,score,email,joined,tag\n")
            for i in range(n):
                out.write("%d,name %d,city%d,%d,%.2f,user%d@example.org,2026-%02d-%02d,t%d\n" % (
                    i, i, rnd.randint(0, 999), rnd.randint(18, 90), rnd.random() * 100, i,
                    rnd.randint(1, 12), rnd.randint(1, 28), rnd.randint(0, 9)))
        os.rename(f + ".part", f)
        return True

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        src = os.path.join(WL, "flat", "flat-csv.rml.ttl")
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": _rewrite(src, os.path.join(work, "mapping-abs.rml.ttl"),
                                     '"rows.csv"', '"%s/rows.csv"' % d),
            "rml_relative": src,
            "sg_query": os.path.join(WL, "flat", "flat-csv.rqg"),
            "sa_query": os.path.join(WL, "flat", "flat-csv.sa.sparql"),
            "sg_base": self.sg_base, "rml_base": self.rml_base,
        }


class KGCW(Workload):
    """A task of the KGCW Challenge 2024, track 2 (scripts/fetch_kgcw.sh). The
    tasks load CSV files into MySQL and map the tables (rml:SQL2008TableName,
    RML-Core); here the mapping reads the same CSV files, in the RML 1.x
    vocabulary that every engine of the benchmark reads (to_rml1).
    One size per task: scale 1."""

    TASKS = {
        "records-100K": "records/100K_rows_20_columns",
        "records-1M": "records/1M_rows_20_columns",
        "properties-1M-10": "properties/1M_rows_10_columns",
        "duplicates-50": "duplicated-values/50percent",
        "empty-50": "empty-values/50percent",
        "mappings-15tm-1pom": "mappings/mapping_15tm_1pom",
        "join-1-1-50": "joins/join_1-1/join_1-1_50percent",
        "join-1-N-50": "joins/join_1-N/join_1-10_50percent",
        "join-N-M-50": "joins/join_N-M/join_5-5_50percent",
    }

    def __init__(self, task):
        self.task = task
        self.name = "kgcw-" + task

    def data_dir(self, scale):
        return os.path.join(DATA, "kgcw-2024", "track2", self.TASKS[self.task], "data", "shared")

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        mapping = os.path.join(work, "mapping.rml.ttl")
        to_rml1(os.path.join(d, "mapping.rml.ttl"), mapping, d)
        return {"workload": self.name, "scale": scale, "data": d,
                "rml_absolute": mapping, "rml_relative": mapping,
                "sg_query": None, "sa_query": None,
                "sg_base": self.sg_base, "rml_base": self.rml_base}


def to_rml1(src, out, data_dir):
    """An RML-Core mapping over SQL tables (KGCW 2024, track 2) as an RML 1.x
    mapping over the CSV files of the same tables (rml:source "<dir>/<table>.csv"),
    the vocabulary that every engine of the benchmark reads."""
    from rdflib import Graph, Literal, Namespace, URIRef, BNode
    from rdflib.namespace import RDF
    RMLC = Namespace("http://w3id.org/rml/")
    RR = Namespace("http://www.w3.org/ns/r2rml#")
    RML = Namespace("http://semweb.mmlab.be/ns/rml#")
    QL = Namespace("http://semweb.mmlab.be/ns/ql#")
    to_rml = {"logicalSource", "source", "referenceFormulation", "iterator", "reference",
              "LogicalSource"}
    g = Graph()
    g.parse(src, format="turtle")
    h = Graph()
    tables = {}
    for ls in set(g.objects(None, RMLC.logicalSource)):
        tables[ls] = str(g.value(ls, RMLC.iterator))

    def term(t):
        if isinstance(t, URIRef) and str(t).startswith(str(RMLC)):
            local = str(t)[len(str(RMLC)):]
            if local in to_rml:
                return RML[local]
            if local == "CSV":
                return QL.CSV
            return RR[local]
        return t
    for s, p, o in g:
        if s in tables:
            continue
        if str(p).startswith("http://www.wiwiss.fu-berlin.de/suhl/bizer/D2RQ"):
            continue
        h.add((term(s), term(p), term(o)))
    for ls, table in tables.items():
        h.add((ls, RML.source, Literal(os.path.join(data_dir, table + ".csv"))))
        h.add((ls, RML.referenceFormulation, QL.CSV))
    h.bind("rr", RR)
    h.bind("rml", RML)
    h.bind("ql", QL)
    h.serialize(out, format="turtle")
    return out


ALL = {w.name: w for w in [GTFS(), Nested("json"), Nested("xml"), FlatCSV()]
       + [KGCW(t) for t in KGCW.TASKS]}
