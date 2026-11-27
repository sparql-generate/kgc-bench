"""The workloads of RQ3. A workload prepares, for one scale, a *job*: the
data directory, the RML mapping (with absolute paths, and with paths
relative to the data directory for rml2sparql-generate), the hand-written
SPARQL-Generate query, the SPARQL Anything query, and the base IRIs.

gtfs         GTFS-Madrid-Bench, CSV distribution, official mapping (13 triples
             maps, 9 joins); data from the benchmark's generator
             (scripts/gtfs_data.sh N)
gtfs-inverted  the same data and mapping, every IRI-valued branch (23 of the 86
             object maps: IRI templates, IRI columns, joins) inverted, ?o inv:p ?s:
             36 triples maps in RML, one GENERATE per file in SPARQL-Generate
gtfs-feeds   K feeds of GTFS-Madrid-Bench at scale 1 (scale = K), one set of files per
             feed (STOPS-f0001.csv, ...), listed in FEEDS.csv; every IRI carries its
             feed. In RML the mapping is instantiated per feed (13 triples maps and 9
             joins per feed, a mapping of K times the size); in SPARQL-Generate one
             query, of the size of gtfs-csv.rqg, iterates FEEDS.csv
gtfs-lists   GTFS-Madrid-Bench, SHAPES.csv: every shape with the RDF list of its points,
             gathered over the rows of the shape (RML-CC, a collection appended across
             iterations); LIST with GROUP BY in SPARQL-Generate
gtfs-lv-join GTFS-Madrid-Bench: every stop time with a label made of values of its trip
             and of its stop, and the route of its trip (RML-LV, a logical view with two
             joins); two look-ups in a graph of keys in SPARQL-Generate
nested-json  synthetic nested JSON: N people, each with an address object and
             3 items; two iterations ($.people[*], $.people[*].items[*]) and
             a multi-valued reference ($.items[*].type); scale = N / 1000
nested-local the people of nested-json, their items numbered in their person only (n):
             the IRI of an item needs the identifier of its person, which RML-Core
             cannot reach from a JSONPath iteration; the mapping is an RML-LV logical
             view (new RML vocabulary), the query a nested GENERATE
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


def _if_exists(path):
    return path if os.path.exists(path) else None


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
    files = os.path.join(WL, "gtfs", "gtfs-csv")   # .rqg, .sa.sparql, .shexml

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": _rewrite(self.mapping, os.path.join(work, "mapping-abs.rml.ttl"),
                                     '"/data/', '"%s/' % d),
            "rml_relative": _rewrite(self.mapping, os.path.join(work, "mapping-rel.rml.ttl"),
                                     '"/data/', '"'),
            "sg_query": self.files + ".rqg",
            "sa_query": self.files + ".sa.sparql",
            # ShExML, a language of its own (scripts/gtfs_mappings.py)
            "shexml_mapping": _if_exists(self.files + ".shexml"),
            "sg_base": self.sg_base, "rml_base": self.rml_base,
        }


class GTFSInverted(GTFS):
    """GTFS-Madrid-Bench, its IRI-valued branches inverted (?o inv:p ?s): the same
    data, the same values and joins; in RML one triples map per inverted branch
    (36), in SPARQL-Generate one GENERATE per file (scripts/gtfs_mappings.py)."""
    name = "gtfs-inverted"
    mapping = os.path.join(WL, "gtfs-inverted", "gtfs-inverted-csv.rml.ttl")
    files = os.path.join(WL, "gtfs-inverted", "gtfs-inverted-csv")

    def data_dir(self, scale):
        return os.path.join(DATA, "gtfs", str(scale))


class GTFSModule(GTFS):
    """A workload on the data of GTFS-Madrid-Bench whose mapping needs an RML module
    (RML-CC, RML-LV): written in the RML of the W3C CG, for the engines that read it."""

    def __init__(self, name):
        self.name = name
        self.mapping = os.path.join(WL, name, name + ".rml.ttl")
        self.files = os.path.join(WL, name, name)

    def data_dir(self, scale):
        return os.path.join(DATA, "gtfs", str(scale))

    def job(self, scale, work):
        j = super().job(scale, work)
        j["sa_query"] = j["shexml_mapping"] = None
        return j


class GTFSFeeds(Workload):
    """K feeds of the same schema, whose identifiers are unique in their feed only
    (a catalogue of GTFS feeds). scale = K. The data of every feed is that of
    GTFS-Madrid-Bench at scale 1 (the same rows: only the IRIs differ, by the feed);
    the RML mapping is the official one, once per feed, with the feed in the names
    of the triples maps, in the paths and in the IRI templates (untimed: a mapping language without a source that
    depends on data needs a generated mapping)."""
    name = "gtfs-feeds"
    sg_base = "http://transport.linkeddata.es/"
    mapping = os.path.join(ROOT, "third_party", "gtfs-bench", "mappings", "gtfs-csv.rml.ttl")
    files = os.path.join(WL, "gtfs-feeds", "gtfs-feeds-csv")
    seed = os.path.join(DATA, "gtfs", "1")

    @staticmethod
    def feeds(scale):
        return ["f%04d" % i for i in range(1, int(scale) + 1)]

    def ensure_data(self, scale):
        d = self.data_dir(scale)
        if os.path.exists(os.path.join(d, "FEEDS.csv")):
            return True
        if not os.path.isdir(self.seed):
            return False
        os.makedirs(d, exist_ok=True)
        for feed in self.feeds(scale):
            for f in sorted(os.listdir(self.seed)):
                if f.endswith(".csv"):
                    dst = os.path.join(d, "%s-%s.csv" % (f[:-4], feed))
                    if not os.path.lexists(dst):
                        os.symlink(os.path.realpath(os.path.join(self.seed, f)), dst)
        with open(os.path.join(d, "FEEDS.csv.part"), "w", encoding="utf-8") as out:
            out.write("feed\n" + "".join(feed + "\n" for feed in self.feeds(scale)))
        os.rename(os.path.join(d, "FEEDS.csv.part"), os.path.join(d, "FEEDS.csv"))
        return True

    def _mapping(self, scale, out, directory):
        """The official mapping once per feed: its triples maps renamed (<f0001_stops_0>;
        one @base for the file, since FlexRML 3.1.0 reads the first one only), its
        files, its IRIs."""
        import re
        text = open(self.mapping, encoding="utf-8").read()
        head = "".join(l for l in text.splitlines(True) if l.startswith("@"))
        body = "".join(l for l in text.splitlines(True) if not l.startswith("@"))
        with open(out, "w", encoding="utf-8") as f:
            f.write(head)
            for feed in self.feeds(scale):
                t = re.sub(r"<(\w+_0)>", lambda m: "<%s_%s>" % (feed, m.group(1)), body)
                t = re.sub(r'"/data/([A-Z_]+)\.csv"', lambda m: '"%s%s-%s.csv"' % (directory, m.group(1), feed), t)
                f.write(t.replace("http://transport.linkeddata.es/madrid/",
                                  "http://transport.linkeddata.es/%s/" % feed) + "\n")
        return out

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": self._mapping(scale, os.path.join(work, "mapping-abs.rml.ttl"), d + "/"),
            "rml_relative": self._mapping(scale, os.path.join(work, "mapping-rel.rml.ttl"), ""),
            "sg_query": self.files + ".rqg", "sa_query": None,
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


class NestedLocal(Workload):
    """nested-json with items numbered in their person only: an RML-LV mapping."""
    name = "nested-local"
    sg_base = "http://example.org/"

    def ensure_data(self, scale):
        d = self.data_dir(scale)
        f = os.path.join(d, "people.json")
        if os.path.exists(f):
            return True
        os.makedirs(d, exist_ok=True)
        n = int(scale * 1000)
        rnd = random.Random(42)
        cities = ["Paris", "Lyon", "Saint-Etienne", "Madrid", "Gent", "Bologna"]
        types = ["book", "pen", "cup", "lamp", "phone", "bag"]
        with open(f + ".part", "w", encoding="utf-8") as out:
            out.write('{"people":[\n')
            for i in range(n):
                p = {"id": i, "name": "person %d" % i,
                     "address": {"city": rnd.choice(cities), "zip": "%05d" % rnd.randint(0, 99999)},
                     "items": [{"n": k + 1, "type": rnd.choice(types), "weight": rnd.randint(1, 500)}
                               for k in range(3)]}
                out.write(("," if i else "") + json.dumps(p, separators=(",", ":")) + "\n")
            out.write("]}\n")
        os.rename(f + ".part", f)
        return True

    def job(self, scale, work):
        d = self.data_dir(scale)
        os.makedirs(work, exist_ok=True)
        src = os.path.join(WL, "nested-local", "nested-local-json.rml.ttl")
        return {
            "workload": self.name, "scale": scale, "data": d,
            "rml_absolute": _rewrite(src, os.path.join(work, "mapping-abs.rml.ttl"),
                                     '"people.', '"%s/people.' % d),
            "rml_relative": src,
            "sg_query": os.path.join(WL, "nested-local", "nested-local-json.rqg"),
            "sa_query": None, "sg_base": self.sg_base, "rml_base": self.rml_base,
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


ALL = {w.name: w for w in [GTFS(), GTFSInverted(), GTFSFeeds(), GTFSModule("gtfs-lists"), GTFSModule("gtfs-lv-join"), NestedLocal(), Nested("json"), Nested("xml"), FlatCSV()]
       + [KGCW(t) for t in KGCW.TASKS]}


def load_external(env=None):
    """The workloads of other packages, added to ALL: every entry point of the group
    ``kgc_bench.workloads`` (``[project.entry-points."kgc_bench.workloads"]`` of their
    pyproject.toml), and every ``module`` or ``module:attribute`` of KGC_BENCH_WORKLOADS
    (comma-separated). The object named is a workload, an iterable of workloads, or a
    callable that returns one of them. Two workloads of one name are an error. Returns the
    names added."""
    import importlib
    from importlib.metadata import entry_points
    env = os.environ if env is None else env
    found = [ep.load() for ep in entry_points(group="kgc_bench.workloads")]
    for spec in filter(None, (x.strip() for x in env.get("KGC_BENCH_WORKLOADS", "").split(","))):
        module, _, attr = spec.partition(":")
        obj = importlib.import_module(module)
        found.append(getattr(obj, attr or "WORKLOADS"))
    added = []
    for obj in found:
        if callable(obj) and not hasattr(obj, "job"):
            obj = obj()
        for w in ([obj] if hasattr(obj, "job") else list(obj)):
            if w.name in ALL and ALL[w.name] is not w:
                raise ValueError("two workloads named %s" % w.name)
            ALL[w.name] = w
            added.append(w.name)
    return added


load_external()


def to_rml_core(src, out, null=""):
    """A legacy RML mapping (R2RML rr: + http://semweb.mmlab.be/ns/rml#, ql:) in the
    RML of the W3C KG-Construct CG (http://w3id.org/rml/), for an engine that reads
    only the latter (BURP): rr: and the legacy rml: terms renamed, ql:CSV and the
    other reference formulations to rml:, a file name source to an rml:FilePath
    source with rml:path; the empty CSV cell declared NULL (rml:null), as the legacy
    engines read it (null: None for no rml:null)."""
    from rdflib import BNode, Graph, Literal, Namespace, URIRef
    from rdflib.namespace import RDF
    NEW = Namespace("http://w3id.org/rml/")
    OLD = ("http://www.w3.org/ns/r2rml#", "http://semweb.mmlab.be/ns/rml#",
           "http://semweb.mmlab.be/ns/ql#")
    g = Graph()
    g.parse(src, format="turtle")
    h = Graph()

    def term(t):
        if isinstance(t, URIRef):
            for ns in OLD:
                if str(t).startswith(ns):
                    local = str(t)[len(ns):]
                    return NEW[{"column": "reference"}.get(local, local)]
        return t
    sources = {}
    for s, p, o in g:
        if p == URIRef(OLD[1] + "source") and isinstance(o, Literal):
            sources[s] = str(o)
            continue
        h.add((term(s), term(p), term(o)))
    for ls, path in sources.items():
        b = BNode()
        h.add((ls, NEW.source, b))
        h.add((b, RDF.type, NEW.FilePath))
        h.add((b, NEW.path, Literal(path)))
        if null is not None:
            h.add((b, NEW.null, Literal(null)))
    h.bind("rml", NEW)
    h.serialize(out, format="turtle")
    return out
