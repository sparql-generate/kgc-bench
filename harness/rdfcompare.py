"""The oracle: RDF dataset isomorphism, named graphs included.

Two outputs are equivalent when they have the same set of non-empty named
graphs (the default graph counting as one) and pairwise isomorphic graphs.
Outputs are never compared as text. Adapted from the kgc-study harness
(runner.py) of the same author.
"""

import os
import subprocess

import hashlib
import re
import shutil
import tempfile

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.compare import isomorphic, to_isomorphic, graph_diff

FORMATS = {".nq": "nquads", ".nt": "nquads", ".ttl": "turtle",
           ".trig": "trig", ".n3": "n3", ".rdf": "xml", ".rdfxml": "xml",
           ".jsonld": "json-ld", ".rdfjson": "rdf-json"}

# compressed outputs (RML-IO targets): extension -> how to read the one file inside
COMPRESSIONS = (".gz", ".zip", ".tar.xz", ".tar.gz")

# RDF-star: a quoted triple << s p o >> becomes a blank node b with the three
# triples b STAR_S s, b STAR_P p, b STAR_O o (one blank node per distinct
# quoted triple of a document), so that RDF-star isomorphism is checked as
# plain RDF isomorphism. Every side is encoded alike.
STAR = "https://w3id.org/kgc-bench/rdf-star#"
STAR_S, STAR_P, STAR_O = (URIRef(STAR + x) for x in ("subject", "predicate", "object"))


def load_dataset(path, fmt=None):
    """Parse an RDF file into a Dataset. N-Triples is read as N-Quads (it is
    a subset), so that every engine's output goes through the same parser.

    Two normalisations, applied to every side alike: a literal typed
    xsd:string is the simple literal (RDF 1.1); and when an N-Quads file
    holds IRIs with spaces (rml:UnsafeIRI, RML-Core 0027b), which the parser
    rejects, the spaces are written %20 before parsing."""
    ds = Dataset(default_union=False)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return ds
    for ext in COMPRESSIONS:
        if path.endswith(ext) and not fmt:
            with tempfile.TemporaryDirectory(prefix="kgcb-unpack-") as d:
                inner = decompress(path, d)
                return load_dataset(inner, None) if inner else ds
    fmt = fmt or FORMATS.get(os.path.splitext(path)[1], "nquads")
    if fmt == "rdf-json":
        return _normalise(_load_rdf_json(path))
    if fmt == "nquads" and _is_star(path):
        return _normalise(_load_star(path))
    if fmt in ("nquads", "trig"):
        try:
            ds.parse(path, format=fmt)
        except Exception:
            if fmt != "nquads":
                raise
            ds = Dataset(default_union=False)
            text = open(path, encoding="utf-8").read()
            text = re.sub(r"<[^<>\"\n]*>", lambda m: m.group(0).replace(" ", "%20"), text)
            with tempfile.NamedTemporaryFile("w", suffix=".nq", delete=False,
                                             encoding="utf-8") as f:
                f.write(text)
            ds.parse(f.name, format=fmt)
            os.unlink(f.name)
    else:
        g = Graph()
        g.parse(path, format=fmt)
        for t in g:
            ds.default_context.add(t)
    return _normalise(ds)


def decompress(path, into):
    """The file inside a compressed output (gzip, zip, tar.xz, tar.gz),
    extracted into the directory into, named after the archive without its
    compression extension (a member's own name for zip and tar); None when
    the archive holds no file."""
    import gzip
    import tarfile
    import zipfile
    if path.endswith((".tar.xz", ".tar.gz")):
        with tarfile.open(path) as t:
            members = [m for m in t.getmembers() if m.isfile()]
            if not members:
                return None
            out = os.path.join(into, os.path.basename(members[0].name))
            with t.extractfile(members[0]) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return out
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            if not names:
                return None
            out = os.path.join(into, os.path.basename(names[0]))
            with z.open(names[0]) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return out
    out = os.path.join(into, os.path.basename(path)[:-len(".gz")])
    with gzip.open(path, "rb") as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return out


def _load_rdf_json(path):
    """RDF 1.1 JSON Alternate Serialization (RDF/JSON), which rdflib does not
    read: {subject: {predicate: [{type, value, lang?, datatype?}]}}."""
    import json
    ds = Dataset(default_union=False)

    def term(v):
        if v.startswith("_:"):
            return BNode(v[2:])
        return URIRef(v)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    for s, preds in doc.items():
        for p, objs in preds.items():
            for o in objs:
                if o["type"] == "literal":
                    obj = Literal(o["value"], lang=o.get("lang"),
                                  datatype=URIRef(o["datatype"]) if o.get("datatype") else None)
                elif o["type"] == "bnode":
                    obj = BNode(o["value"][2:] if o["value"].startswith("_:") else o["value"])
                else:
                    obj = URIRef(o["value"])
                ds.default_context.add((term(s), URIRef(p), obj))
    return ds


def _is_star(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return any("<<" in line for line in f)


def _load_star(path):
    """N-Triples-star / N-Quads-star, read with pyoxigraph (rdflib has no
    RDF-star parser), each quoted triple encoded as a blank node (STAR)."""
    import pyoxigraph as ox
    ds = Dataset(default_union=False)
    quoted = {}       # (graph name, quoted triple) -> blank node
    extra = []
    graph = [None]    # the graph of the quad being read

    def term(t):
        if isinstance(t, ox.Triple):
            key = (graph[0], term(t.subject), term(t.predicate), term(t.object))
            if key not in quoted:
                b = quoted[key] = BNode("q%d" % len(quoted))
                extra.extend([(b, STAR_S, key[1]), (b, STAR_P, key[2]), (b, STAR_O, key[3])])
            return quoted[key]
        if isinstance(t, ox.NamedNode):
            return URIRef(t.value)
        if isinstance(t, ox.BlankNode):
            return BNode("b" + t.value)
        if isinstance(t, ox.Literal):
            dt = t.datatype.value if t.datatype else None
            if t.language:
                return Literal(t.value, lang=t.language)
            return Literal(t.value, datatype=URIRef(dt) if dt and not dt.endswith(
                "#string") else None)
        return None  # the default graph
    with open(path, "rb") as f:
        for q in ox.parse(f, "application/n-quads"):
            g = getattr(q, "graph_name", None)
            gname = None if g is None or isinstance(g, ox.DefaultGraph) else term(g)
            graph[0] = gname
            target = ds.default_context if gname is None else ds.graph(gname)
            target.add((term(q.subject), term(q.predicate), term(q.object)))
            for t in extra:
                target.add(t)
            extra.clear()
    return ds


def _normalise(ds):
    def n(t):
        if isinstance(t, Literal) and t.datatype == XSD.string:
            return Literal(str(t))
        return t
    if not any(isinstance(o, Literal) and o.datatype == XSD.string
               for _, _, o, _ in ds.quads((None, None, None, None))):
        return ds
    out = Dataset(default_union=False)
    default = ds.default_context.identifier
    for s, p, o, g in ds.quads((None, None, None, None)):
        gid = g.identifier if hasattr(g, "identifier") else g
        target = out.default_context if gid is None or gid == default else out.graph(gid)
        target.add((s, p, n(o)))
    return out


# Skolem IRIs of earlier versions of rml2sparql-generate
GENID = "https://w3id.org/sparql-generate/.well-known/genid/"


def deskolemize(ds, prefix=GENID):
    """delta: every IRI with the Skolem prefix becomes a blank node,
    injectively (one blank node per IRI)."""
    def d(t):
        if isinstance(t, URIRef) and str(t).startswith(prefix):
            return BNode("sk" + hashlib.md5(str(t).encode()).hexdigest())
        return t
    out = Dataset(default_union=False)
    default = ds.default_context.identifier
    for s, p, o, g in ds.quads((None, None, None, None)):
        gid = g.identifier if hasattr(g, "identifier") else g
        q = (d(s), p, d(o))
        if gid is None or gid == default:
            out.default_context.add(q)
        else:
            out.graph(gid).add(q)
    return out


def graphs_by_name(ds):
    """{graph name (None for the default graph): Graph} — non-empty graphs."""
    out = {}
    default = ds.default_context.identifier
    for ctx in ds.contexts():
        g = Graph()
        for t in ctx:
            g.add(t)
        if len(g) == 0:
            continue
        out[None if ctx.identifier == default else ctx.identifier] = g
    return out


def _has_bnodes(g):
    return any(isinstance(t, BNode) for tr in g for t in tr)


def datasets_isomorphic(a, b):
    """(True, '') or (False, a short explanation of the first difference).
    Graphs without blank nodes are compared as sets of triples: rdflib's
    canonicalisation (isomorphic, to_isomorphic) of a large graph takes tens
    of gigabytes."""
    ga, gb = graphs_by_name(a), graphs_by_name(b)
    if set(ga) != set(gb):
        return False, "different named graphs: got %s, expected %s" % (
            sorted(map(str, ga)), sorted(map(str, gb)))
    for name in ga:
        if not _has_bnodes(ga[name]) and not _has_bnodes(gb[name]):
            sa, sb = set(ga[name]), set(gb[name])
            if sa != sb:
                ex_a = min(sa - sb, default=None)
                ex_b = min(sb - sa, default=None)
                return False, "graph %s differs (%d vs %d triples, %d and %d apart); extra: %s; missing: %s" % (
                    name or "(default)", len(sa), len(sb), len(sa - sb), len(sb - sa),
                    _short(ex_a), _short(ex_b))
            continue
        if not isomorphic(ga[name], gb[name]):
            _, only_a, only_b = graph_diff(to_isomorphic(ga[name]),
                                           to_isomorphic(gb[name]))
            ex_a = next(iter(sorted(only_a.triples((None, None, None)))), None)
            ex_b = next(iter(sorted(only_b.triples((None, None, None)))), None)
            return False, "graph %s differs (%d vs %d triples); extra: %s; missing: %s" % (
                name or "(default)", len(ga[name]), len(gb[name]),
                _short(ex_a), _short(ex_b))
    return True, ""


def _short(t):
    if t is None:
        return "-"
    return " ".join(x.n3() for x in t)[:160]


def count_quads(path):
    """Number of distinct non-blank lines of an N-Triples/N-Quads file: the
    triple count used at scales too large for an in-memory isomorphism check
    (each engine serialises a given term always the same way)."""
    if not path or not os.path.exists(path):
        return None
    return count_distinct_lines(path, "grep -v '^[[:space:]]*$' %s | grep -v '^#'" % _q(path))


def count_distinct_lines(path, producer):
    """Distinct lines printed by the shell pipeline producer, sorted with a
    bounded buffer (1G, spilling next to the file) in a memory-capped scope."""
    from harness import sandbox
    tmp = os.path.dirname(os.path.abspath(path))
    # the spill files are compressed (zstd, when installed): uncompressed, they are as
    # large as the output itself
    import shutil
    zst = " --compress-program=zstd" if shutil.which("zstd") else ""
    cmd = "%s | sort -u -S 2G -T %s --parallel=4%s | wc -l" % (producer, _q(tmp), zst)
    r = sandbox.run(["sh", "-c", cmd], None, env=dict(os.environ, LC_ALL="C"))
    if r["status"] != "ok":
        raise RuntimeError("counting the triples of %s: %s %s" % (path, r["status"],
                                                                 r["stderr"][-200:]))
    return int(r["stdout"].strip() or 0)


def _q(p):
    return "'" + p.replace("'", "'\\''") + "'"
