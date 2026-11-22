"""Runs a query file on an empty dataset with a Python SPARQL engine, writing
SPARQL JSON results (SELECT) or N-Triples (CONSTRUCT).

    python run_python.py rdflib|oxigraph query.rq out
"""

import json
import sys


def term_json(t):
    """A term as in the SPARQL 1.1 JSON results format."""
    import rdflib
    if t is None:
        return None
    if isinstance(t, rdflib.URIRef):
        return {"type": "uri", "value": str(t)}
    if isinstance(t, rdflib.BNode):
        return {"type": "bnode", "value": str(t)}
    d = {"type": "literal", "value": str(t)}
    if t.language:
        d["xml:lang"] = t.language
    elif t.datatype:
        d["datatype"] = str(t.datatype)
    return d


def ox_json(t):
    import pyoxigraph as ox
    if t is None:
        return None
    if isinstance(t, ox.NamedNode):
        return {"type": "uri", "value": t.value}
    if isinstance(t, ox.BlankNode):
        return {"type": "bnode", "value": t.value}
    d = {"type": "literal", "value": t.value}
    if t.language:
        d["xml:lang"] = t.language
    elif t.datatype and t.datatype.value != "http://www.w3.org/2001/XMLSchema#string":
        d["datatype"] = t.datatype.value
    return d


def main(engine, qfile, out):
    q = open(qfile, encoding="utf-8").read()
    if engine == "rdflib":
        import rdflib
        res = rdflib.Graph().query(q)
        if res.type == "CONSTRUCT":
            res.graph.serialize(out, format="nt")
            return
        vars_ = [str(v) for v in res.vars]
        rows = [{v: term_json(r[i]) for i, v in enumerate(vars_) if r[i] is not None} for r in res]
    else:
        import pyoxigraph as ox
        res = ox.Store().query(q)
        if isinstance(res, ox.QueryTriples):
            with open(out, "w", encoding="utf-8") as f:
                for t in res:
                    f.write("%s %s %s .\n" % (t.subject, t.predicate, t.object))
            return
        vars_ = [v.value for v in res.variables]
        rows = [{v: ox_json(s[v]) for v in vars_ if s[v] is not None} for s in res]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"head": {"vars": vars_}, "results": {"bindings": rows}}, f)


if __name__ == "__main__":
    main(*sys.argv[1:4])
