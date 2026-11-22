"""Writes the queries of the slicing scenario (queries/): the same 15 questions
over people.csv, people.json and people.xml, for SPARQL Anything (sa/<format>/,
%DATA% and %OPTIONS% to be replaced), and their SPARQL-Generate counterparts
over CSV and JSON (sg/<format>/, %BATCH% to be replaced by "" or ", <n>").

    python make_queries.py

The queries are generated from one table so that the three formats ask
exactly the same questions; the generated files are versioned, to be read.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "queries")

PREFIXES = """PREFIX xyz: <http://sparql.xyz/facade-x/data/>
PREFIX fx:  <http://sparql.xyz/facade-x/ns/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# location and the options every configuration shares, per format
LOCATION = {
    "csv": "x-sparql-anything:location=%DATA%/people.csv,csv.headers=true%OPTIONS%",
    "json": "x-sparql-anything:location=%DATA%/people.json%OPTIONS%",
    "xml": "x-sparql-anything:location=%DATA%/people.xml,xml.path=//person%OPTIONS%",
}


def row(fmt, s=""):
    """The pattern of one person in the facade: ?r ?id ?name ?city ?score."""
    if fmt == "xml":
        return ("?r{s} a xyz:person ; xyz:id ?id{s} ;\n"
                "      fx:anySlot [ a xyz:name ; rdf:_1 ?name{s} ] , [ a xyz:city ; rdf:_1 ?city{s} ] ,\n"
                "                 [ a xyz:score ; rdf:_1 ?score{s} ] .").format(s=s)
    return "?r{s} xyz:id ?id{s} ; xyz:name ?name{s} ; xyz:city ?city{s} ; xyz:score ?score{s} .".format(s=s)


def manager(fmt, s=""):
    if fmt == "xml":
        return "?r{s} fx:anySlot [ a xyz:manager ; rdf:_1 ?manager{s} ] .".format(s=s)
    if fmt == "csv":
        return '?r{s} xyz:manager ?manager{s} . FILTER(?manager{s} != "")'.format(s=s)
    return "?r{s} xyz:manager ?manager{s} .".format(s=s)


SCORE = "xsd:integer(STR(?score))"

# (name, what it asks, where the operator is: "inside" the SERVICE clause,
#  "outside" it, or "plain", the SPARQL Anything query)
SA = [
    ("q01-rows", "every person", "plain",
     "SELECT ?id ?name WHERE {{ SERVICE <{L}> {{\n  {R}\n}} }}"),
    ("q02-filter", "people with a score of 50 or more", "plain",
     "SELECT ?name WHERE {{ SERVICE <{L}> {{\n  {R}\n  FILTER(" + SCORE + " >= 50)\n}} }}"),
    ("q03-join-city", "pairs of people of the same city (self-join)", "inside",
     "SELECT ?name ?name2 WHERE {{ SERVICE <{L}> {{\n  {R}\n  {R2}\n"
     "  FILTER(STR(?city) = STR(?city2) && STR(?name) < STR(?name2))\n}} }}"),
    ("q04-join-manager", "each person and the name of their manager (join on a key)", "inside",
     "SELECT ?name ?name2 WHERE {{ SERVICE <{L}> {{\n  {R}\n  {M}\n  {R2}\n"
     "  FILTER(STR(?manager) = STR(?id2))\n}} }}"),
    ("q05-exists", "people who share their city with someone else (FILTER EXISTS)", "inside",
     "SELECT ?name WHERE {{ SERVICE <{L}> {{\n  {R}\n  FILTER EXISTS {{\n    {R2}\n"
     "    FILTER(STR(?city2) = STR(?city) && STR(?id2) != STR(?id))\n  }}\n}} }}"),
    ("q06-count-inside", "number of people, COUNT inside SERVICE", "inside",
     "SELECT ?n WHERE {{ SERVICE <{L}> {{\n  SELECT (COUNT(*) AS ?n) WHERE {{\n    {R}\n  }}\n}} }}"),
    ("q07-group-inside", "people per city, GROUP BY inside SERVICE", "inside",
     "SELECT ?city ?n WHERE {{ SERVICE <{L}> {{\n  SELECT ?city (COUNT(*) AS ?n) WHERE {{\n    {R}\n"
     "  }} GROUP BY ?city\n}} }}"),
    ("q08-distinct-inside", "the cities, DISTINCT inside SERVICE", "inside",
     "SELECT ?city WHERE {{ SERVICE <{L}> {{\n  SELECT DISTINCT ?city WHERE {{\n    {R}\n  }}\n}} }}"),
    ("q09-top3-inside", "the three best scores, ORDER BY and LIMIT inside SERVICE", "inside",
     "SELECT ?name WHERE {{ SERVICE <{L}> {{\n  SELECT ?name WHERE {{\n    {R}\n"
     "  }} ORDER BY DESC(" + SCORE + ") ?name LIMIT 3\n}} }}"),
    ("q10-max-inside", "the best score, MAX inside SERVICE", "inside",
     "SELECT ?m WHERE {{ SERVICE <{L}> {{\n  SELECT (MAX(" + SCORE + ") AS ?m) WHERE {{\n    {R}\n"
     "  }}\n}} }}"),
    ("q11-next", "each person and the next one in the file (fx:next)", "inside",
     "SELECT ?name ?name2 WHERE {{ SERVICE <{L}> {{\n  ?root a fx:Root ; ?s1 ?r ; ?s2 ?r2 .\n"
     "  FILTER(?s2 = fx:next(?s1))\n  {R}\n  {R2}\n}} }}"),
    ("q12-root-slots", "number of slots of the root container", "inside",
     "SELECT ?n WHERE {{ SERVICE <{L}> {{\n  SELECT (COUNT(?r) AS ?n) WHERE {{\n"
     "    ?root a fx:Root ; ?slot ?r . FILTER(STRSTARTS(STR(?slot), STR(rdf:_)))\n  }}\n}} }}"),
    ("q13-group-outside", "people per city, GROUP BY outside SERVICE", "outside",
     "SELECT ?city (COUNT(*) AS ?n) WHERE {{ SERVICE <{L}> {{\n  {R}\n}} }} GROUP BY ?city"),
    ("q14-top3-outside", "the three best scores, ORDER BY and LIMIT outside SERVICE", "outside",
     "SELECT ?name WHERE {{ SERVICE <{L}> {{\n  {R}\n}} }}\nORDER BY DESC(" + SCORE + ") ?name LIMIT 3"),
    ("q15-join-outside", "pairs of people of the same city, the join outside SERVICE", "outside",
     "SELECT ?name ?name2 WHERE {{\n  SERVICE <{L}> {{ {R} }}\n  SERVICE <{L}> {{ {R2} }}\n"
     "  FILTER(STR(?city) = STR(?city2) && STR(?name) < STR(?name2))\n}}"),
]

# SPARQL-Generate: the iteration is a clause of the query, so the questions
# q11 and q12 (positions in a Facade-X container) have no counterpart, and
# inside/outside is one and the same query. %BATCH% sets the batch size of
# the iterator (iter:CSV, iter:JSONSurfer); the semantics of ITERATOR does
# not depend on it.
SG_PREFIXES = """PREFIX iter: <http://w3id.org/sparql-generate/iter/>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""


def it(fmt, s=""):
    if fmt == "csv":
        return ('ITERATOR iter:CSV(<people.csv>%BATCH%, "id", "name", "city", "manager", "score")\n'
                "    AS ?id{s} ?name{s} ?city{s} ?manager{s} ?score{s}").format(s=s)
    return ('ITERATOR iter:JSONSurfer(<people.json>, "$[*]"%BATCH%, "$.id", "$.name", "$.city",\n'
            '    "$.manager", "$.score") AS ?r{s} ?id{s} ?name{s} ?city{s} ?manager{s} ?score{s}').format(s=s)


def num(fmt):
    return "xsd:integer(?score)" if fmt == "csv" else "?score"


SG = {
    "q01-rows": "SELECT ?id ?name\n{I}\nWHERE {{ }}",
    "q02-filter": "SELECT ?name\n{I}\nWHERE {{ FILTER({N} >= 50) }}",
    "q03-join-city": "SELECT ?name ?name2\n{I}\n{I2}\n"
                     "WHERE {{ FILTER(STR(?city) = STR(?city2) && STR(?name) < STR(?name2)) }}",
    "q04-join-manager": "SELECT ?name ?name2\n{I}\n{I2}\n"
                        "WHERE {{ FILTER(BOUND(?manager) && STR(?manager) = STR(?id2)) }}",
    "q05-exists": "SELECT DISTINCT ?name\n{I}\n{I2}\n"
                  "WHERE {{ FILTER(STR(?city2) = STR(?city) && STR(?id2) != STR(?id)) }}",
    "q06-count-inside": "SELECT (COUNT(*) AS ?n)\n{I}\nWHERE {{ }}",
    "q07-group-inside": "SELECT ?city (COUNT(*) AS ?n)\n{I}\nWHERE {{ }}\nGROUP BY ?city",
    "q08-distinct-inside": "SELECT DISTINCT ?city\n{I}\nWHERE {{ }}",
    "q09-top3-inside": "SELECT ?name\n{I}\nWHERE {{ }}\nORDER BY DESC({N}) ?name LIMIT 3",
    "q10-max-inside": "SELECT (MAX({N}) AS ?m)\n{I}\nWHERE {{ }}",
}


def main():
    for fmt in ("csv", "json", "xml"):
        d = os.path.join(OUT, "sa", fmt)
        os.makedirs(d, exist_ok=True)
        for name, what, where, tpl in SA:
            body = tpl.format(L=LOCATION[fmt], R=row(fmt), R2=row(fmt, "2"), M=manager(fmt))
            with open(os.path.join(d, name + ".rq"), "w", encoding="utf-8") as f:
                f.write("# %s (%s)\n%s\n%s\n" % (what, where, PREFIXES, body))
    for fmt in ("csv", "json"):
        d = os.path.join(OUT, "sg", fmt)
        os.makedirs(d, exist_ok=True)
        for name, what, where, _ in SA:
            if name not in SG:
                continue
            body = SG[name].format(I=it(fmt), I2=it(fmt, "2"), N=num(fmt))
            with open(os.path.join(d, name + ".rqg"), "w", encoding="utf-8") as f:
                f.write("# %s\n%s\n%s\n" % (what, SG_PREFIXES, body))


if __name__ == "__main__":
    main()
