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
import tempfile

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.compare import isomorphic, to_isomorphic, graph_diff

FORMATS = {".nq": "nquads", ".nt": "nquads", ".ttl": "turtle",
           ".trig": "trig", ".n3": "n3", ".rdf": "xml", ".jsonld": "json-ld"}


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
    fmt = fmt or FORMATS.get(os.path.splitext(path)[1], "nquads")
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


def default_graphs_isomorphic(a, b):
    """Isomorphism of the default graphs only."""
    ga, gb = graphs_by_name(a).get(None, Graph()), graphs_by_name(b).get(None, Graph())
    return isomorphic(ga, gb)


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
    cmd = "%s | sort -u -S 1G -T %s --parallel=4 | wc -l" % (producer, _q(tmp))
    r = sandbox.run(["sh", "-c", cmd], None, env=dict(os.environ, LC_ALL="C"))
    if r["status"] != "ok":
        raise RuntimeError("counting the triples of %s: %s %s" % (path, r["status"],
                                                                 r["stderr"][-200:]))
    return int(r["stdout"].strip() or 0)


def _q(p):
    return "'" + p.replace("'", "'\\''") + "'"
