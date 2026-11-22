"""The feature matrix (positioning, argument 8): minimal cases, each with its
input, its expected output, and the query that produces it in SPARQL-Generate
(sg) and in SPARQL Anything (sa), or the reason why one of them cannot
express it (sg_na, sa_na) or why the case is not run here (not_run).

kind: "graph" (expected N-Triples, compared by isomorphism), "quads"
(expected N-Quads), "text" (expected text; SPARQL Anything gives it as the
single value of a SELECT). %DATA% is the directory of the inputs, %PORT% the
port of a local HTTP server (needs: "http").
"""

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
SG = """BASE <http://example.org/>
PREFIX iter: <http://w3id.org/sparql-generate/iter/>
PREFIX fun:  <http://w3id.org/sparql-generate/fn/>
"""
SA = """PREFIX xyz: <http://sparql.xyz/facade-x/data/>
PREFIX fx:  <http://sparql.xyz/facade-x/ns/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""
PEOPLE = "name,city\nAda,Paris\nBob,Lyon\nEve,Paris\n"


def xlsx():
    """A minimal spreadsheet: one sheet, a header row and two rows."""
    import io
    import zipfile
    rows = [("name", "city"), ("Ada", "Paris"), ("Bob", "Lyon")]
    cells = "".join(
        '<row r="%d">%s</row>' % (i + 1, "".join(
            '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % ("AB"[j], i + 1, v)
            for j, v in enumerate(r))) for i, r in enumerate(rows))
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>' % (pkg, rel),
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="People" sheetId="1" r:id="rId1"/></sheets></workbook>' % (main, rel),
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/worksheet" Target="worksheets/sheet1.xml"/></Relationships>' % (pkg, rel),
        "xl/worksheets/sheet1.xml": '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (main, cells),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def cbor():
    """{"name": "kgc", "n": 3} in CBOR (RFC 8949), written by hand."""
    return bytes([0xa2, 0x64]) + b"name" + bytes([0x63]) + b"kgc" + bytes([0x61]) + b"n" + bytes([0x03])


CASES = [
    {"name": "rdf-list", "what": "an ordered rdf:List of the values of a JSON array",
     "kind": "graph", "files": {"list.json": '{"items": ["a", "b", "c"]}\n'},
     "expected": """<http://example.org/s> <http://example.org/items> _:l1 .
_:l1 <{R}first> "a" .
_:l1 <{R}rest> _:l2 .
_:l2 <{R}first> "b" .
_:l2 <{R}rest> _:l3 .
_:l3 <{R}first> "c" .
_:l3 <{R}rest> <{R}nil> .
""".replace("{R}", RDF),
     "sg": SG + """GENERATE { <s> <items> LIST(?v) . }
ITERATOR iter:JSONPath(<list.json>, "$.items[*]") AS ?v""",
     "sa": SA + """CONSTRUCT { <http://example.org/s> <http://example.org/items> ?head .
            ?node rdf:first ?v ; rdf:rest ?rest . }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/list.json> {
    ?root xyz:items ?arr . ?arr ?slot ?v . FILTER(STRSTARTS(STR(?slot), STR(rdf:_)))
    OPTIONAL { ?arr ?next ?nv . FILTER(?next = fx:next(?slot)) }
  }
  BIND(fx:bnode(STR(?slot)) AS ?node)
  BIND(IF(BOUND(?nv), fx:bnode(STR(fx:next(?slot))), rdf:nil) AS ?rest)
  BIND(IF(?slot = rdf:_1, ?node, ?none) AS ?head)
}"""},
    {"name": "html-text", "what": "an HTML list (text, not RDF) from a CSV file",
     "kind": "text", "files": {"people.csv": PEOPLE},
     "expected": "<ul><li>Ada (Paris)</li><li>Bob (Lyon)</li><li>Eve (Paris)</li></ul>",
     "sg": SG + """TEMPLATE {
  before = "<ul>" ;
  "<li>" ?name " (" ?city ")</li>"
  ; separator = ""
  ; after = "</ul>"
}
ITERATOR iter:CSV(<people.csv>, "name", "city") AS ?name ?city
WHERE { }
ORDER BY ?name""",
     "sa": SA + """SELECT (CONCAT("<ul>", GROUP_CONCAT(?li; SEPARATOR=""), "</ul>") AS ?text) WHERE {
  { SELECT ?li WHERE {
      SERVICE <x-sparql-anything:location=%DATA%/people.csv,csv.headers=true> {
        ?r xyz:name ?name ; xyz:city ?city }
      BIND(CONCAT("<li>", ?name, " (", ?city, ")</li>") AS ?li)
    } ORDER BY ?li }
}"""},
    {"name": "tree", "what": "the parent-child pairs of a JSON tree of unknown depth",
     "kind": "graph",
     "files": {"tree.json": '{"name": "a", "children": [{"name": "b", "children": [{"name": "c", '
                            '"children": []}]}, {"name": "d"}]}\n'},
     "expected": """<http://example.org/node/a> <http://example.org/child> <http://example.org/node/b> .
<http://example.org/node/a> <http://example.org/child> <http://example.org/node/d> .
<http://example.org/node/b> <http://example.org/child> <http://example.org/node/c> .
""",
     "sg": SG + """GENERATE { GENERATE <tree.rqg>(?doc) . }
SOURCE <tree.json> AS ?doc""",
     "sg_files": {"tree.rqg": SG + """GENERATE <tree.rqg>(?node) {
  <node/{?name}> <child> <node/{?cname}> .
  GENERATE <tree.rqg>(?child) .
}
ITERATOR iter:JSONPath(?node, "$.children[*]", "$.name") AS ?child ?cname
WHERE { BIND(fun:JSONPath(?node, "$.name") AS ?name) }"""},
     "sa": SA + """CONSTRUCT { ?p <http://example.org/child> ?c }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/tree.json> {
    ?pn xyz:name ?pname ; xyz:children ?arr . ?arr ?slot ?cn . ?cn xyz:name ?cname .
  }
  BIND(IRI(CONCAT("http://example.org/node/", ?pname)) AS ?p)
  BIND(IRI(CONCAT("http://example.org/node/", ?cname)) AS ?c)
}"""},
    {"name": "join-csv-json", "what": "a join of a CSV file and a JSON file on a key",
     "kind": "graph",
     "files": {"people.csv": "name,cityId\nAda,c1\nBob,c2\nEve,c1\n",
               "cities.json": '[{"id": "c1", "label": "Paris"}, {"id": "c2", "label": "Lyon"}]\n'},
     "expected": """<http://example.org/person/Ada> <http://example.org/livesIn> "Paris" .
<http://example.org/person/Bob> <http://example.org/livesIn> "Lyon" .
<http://example.org/person/Eve> <http://example.org/livesIn> "Paris" .
""",
     "sg": SG + """GENERATE { <person/{?name}> <livesIn> ?label . }
ITERATOR iter:CSV(<people.csv>, "name", "cityId") AS ?name ?cid
ITERATOR iter:JSONPath(<cities.json>, "$[*]", "$.id", "$.label") AS ?c ?id ?label
WHERE { FILTER(STR(?cid) = STR(?id)) }""",
     "sa": SA + """CONSTRUCT { ?p <http://example.org/livesIn> ?label }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/people.csv,csv.headers=true> { ?r xyz:name ?name ; xyz:cityId ?cid }
  SERVICE <x-sparql-anything:location=%DATA%/cities.json> { ?c xyz:id ?id ; xyz:label ?label }
  FILTER(STR(?cid) = STR(?id))
  BIND(IRI(CONCAT("http://example.org/person/", ?name)) AS ?p)
}"""},
    {"name": "bnode-per-value", "what": "one blank node per city, shared by the rows of that city",
     "kind": "graph", "files": {"people.csv": PEOPLE},
     "expected": """<http://example.org/person/Ada> <http://example.org/city> _:p .
<http://example.org/person/Eve> <http://example.org/city> _:p .
<http://example.org/person/Bob> <http://example.org/city> _:l .
_:p <http://example.org/label> "Paris" .
_:l <http://example.org/label> "Lyon" .
""",
     "sg": SG + """GENERATE { <person/{?name}> <city> ?b . ?b <label> ?city . }
ITERATOR iter:CSV(<people.csv>, "name", "city") AS ?name ?city
WHERE { BIND(fun:bnode(?city) AS ?b) }""",
     "sa": SA + """CONSTRUCT { ?p <http://example.org/city> ?b . ?b <http://example.org/label> ?city }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/people.csv,csv.headers=true> { ?r xyz:name ?name ; xyz:city ?city }
  BIND(IRI(CONCAT("http://example.org/person/", ?name)) AS ?p)
  BIND(fx:bnode(?city) AS ?b)
}"""},
    {"name": "json-lines", "what": "JSON Lines: one JSON object per line",
     "kind": "graph", "files": {"lines.jsonl": '{"id": 1, "name": "a"}\n{"id": 2, "name": "b"}\n'},
     "expected": """<http://example.org/item/1> <http://example.org/name> "a" .
<http://example.org/item/2> <http://example.org/name> "b" .
""",
     "sg": SG + """GENERATE { <item/{STR(?id)}> <name> ?n . }
SOURCE <lines.jsonl> AS ?doc
ITERATOR iter:Split(?doc, "\\n") AS ?line
WHERE { BIND(fun:JSONPath(?line, "$.id") AS ?id) BIND(fun:JSONPath(?line, "$.name") AS ?n) }""",
     "sa": SA + """CONSTRUCT { ?i <http://example.org/name> ?n }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/lines.jsonl> { ?o xyz:id ?id ; xyz:name ?n }
  BIND(IRI(CONCAT("http://example.org/item/", STR(?id))) AS ?i)
}"""},
    {"name": "yaml", "what": "a YAML document", "kind": "graph",
     "files": {"doc.yaml": "name: kgc\nitems:\n  - a\n  - b\n"},
     "expected": """<http://example.org/doc> <http://example.org/name> "kgc" .
<http://example.org/doc> <http://example.org/item> "a" .
<http://example.org/doc> <http://example.org/item> "b" .
""",
     "sg_na": "no YAML reader (sources: JSON, CSV, XML, HTML, CBOR, GeoJSON, SQL, text)",
     "sa": SA + """CONSTRUCT { <http://example.org/doc> <http://example.org/name> ?n ;
                                <http://example.org/item> ?i }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/doc.yaml> {
    ?r xyz:name ?n ; xyz:items ?arr . ?arr ?s ?i . FILTER(STRSTARTS(STR(?s), STR(rdf:_)))
  }
}"""},
    {"name": "xlsx", "what": "the rows of a spreadsheet", "kind": "graph",
     "files": {"people.xlsx": xlsx},
     "expected": """<http://example.org/person/Ada> <http://example.org/city> "Paris" .
<http://example.org/person/Bob> <http://example.org/city> "Lyon" .
""",
     "sg_na": "no spreadsheet reader",
     "sa": SA + """CONSTRUCT { ?p <http://example.org/city> ?city }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/people.xlsx> {
    GRAPH ?g { ?row rdf:_1 ?name ; rdf:_2 ?city . FILTER(?name != "name") }
  }
  BIND(IRI(CONCAT("http://example.org/person/", ?name)) AS ?p)
}"""},
    {"name": "markdown-headings", "what": "the headings of a Markdown file", "kind": "graph",
     "files": {"doc.md": "# Title\n\nText.\n\n## Part one\n\nMore.\n\n## Part two\n"},
     "expected": """<http://example.org/doc> <http://example.org/heading> "Title" .
<http://example.org/doc> <http://example.org/heading> "Part one" .
<http://example.org/doc> <http://example.org/heading> "Part two" .
""",
     "sg": SG + """GENERATE { <doc> <heading> ?h . }
SOURCE <doc.md> AS ?doc
ITERATOR iter:Split(?doc, "\\n") AS ?line
WHERE { FILTER(REGEX(?line, "^#+ ")) BIND(REPLACE(?line, "^#+ ", "") AS ?h) }""",
     "sa": SA + """CONSTRUCT { <http://example.org/doc> <http://example.org/heading> ?t }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/doc.md> { GRAPH ?g { ?h a xyz:Heading ; rdf:_1 ?t } }
}"""},
    {"name": "cbor", "what": "a CBOR document", "kind": "graph",
     "files": {"data.cbor": cbor},
     "expected": '<http://example.org/doc> <http://example.org/name> "kgc" .\n',
     "sg": SG + """GENERATE { <doc> <name> ?n . }
SOURCE <data.cbor> AS ?doc
ITERATOR iter:CBOR(?doc, "$.name") AS ?n""",
     "sg_note": "SOURCE reads a file as a string, and iter:CBOR wants the document in base64: "
                "a binary file cannot be read (see cbor-base64)",
     "sa": SA + """CONSTRUCT { <http://example.org/doc> <http://example.org/name> ?n }
WHERE { SERVICE <x-sparql-anything:location=%DATA%/data.cbor> { ?r xyz:name ?n } }"""},
    {"name": "cbor-base64", "what": "the same CBOR document, given in base64 in a text file",
     "kind": "graph", "files": {"data.b64": lambda: __import__("base64").b64encode(cbor()).decode() + "\n"},
     "expected": '<http://example.org/doc> <http://example.org/name> "kgc" .\n',
     "sg": SG + """GENERATE { <doc> <name> ?n . }
SOURCE <data.b64> AS ?doc
ITERATOR iter:CBOR(REPLACE(STR(?doc), "\\\\s", ""), "$.name") AS ?n""",
     "sa_na": "no CBOR triplifier (see cbor)",
     "sg_note": "iter:CBOR decodes the base64, then parses the bytes as JSON (InvalidJsonException, "
                "logged at DEBUG only): a defect of 2.1.0 to 2.2.3"},
    {"name": "named-graphs", "what": "each person in the named graph of their city (quads)",
     "kind": "quads", "files": {"people.csv": PEOPLE},
     "expected": """<http://example.org/person/Ada> <http://example.org/name> "Ada" <http://example.org/graph/Paris> .
<http://example.org/person/Bob> <http://example.org/name> "Bob" <http://example.org/graph/Lyon> .
<http://example.org/person/Eve> <http://example.org/name> "Eve" <http://example.org/graph/Paris> .
""",
     "sg_note": "GENERATE writes triples (quad templates are planned for 2.3): a TEMPLATE writes N-Quads",
     "sg": SG + """TEMPLATE {
  "<http://example.org/person/" ?name "> <http://example.org/name> \\"" ?name "\\" <http://example.org/graph/" ?city "> .\\n"
}
ITERATOR iter:CSV(<people.csv>, "name", "city") AS ?name ?city
WHERE { }""",
     "sa": SA + """CONSTRUCT { GRAPH ?g { ?p <http://example.org/name> ?name } }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/people.csv,csv.headers=true> { ?r xyz:name ?name ; xyz:city ?city }
  BIND(IRI(CONCAT("http://example.org/person/", ?name)) AS ?p)
  BIND(IRI(CONCAT("http://example.org/graph/", ?city)) AS ?g)
}"""},
    {"name": "http-header", "what": "one HTTP GET per CSV row, the body and a response header in the output",
     "kind": "graph", "needs": "http", "files": {"ids.csv": "id\n1\n2\n"},
     "expected": """<http://example.org/item/1> <http://example.org/label> "one" .
<http://example.org/item/1> <http://example.org/version> "7" .
<http://example.org/item/2> <http://example.org/label> "two" .
<http://example.org/item/2> <http://example.org/version> "7" .
""",
     "sg": SG + """GENERATE { <item/{?id}> <label> ?label ; <version> ?v . }
ITERATOR iter:CSV(<ids.csv>, "id") AS ?id
WHERE {
  BIND(fun:HTTPGet(IRI(CONCAT("http://127.0.0.1:%PORT%/item/", ?id))) AS ?resp)
  # fun:HTTPExtractHeader gives the whole header section
  BIND(REPLACE(fun:HTTPExtractHeader(?resp), "^.*X-Version: *([^\\r\\n]*).*$", "$1", "si") AS ?v)
  BIND(fun:JSONPath(fun:HTTPExtractBody(?resp), "$.label") AS ?label)
}""",
     "sa": SA + """CONSTRUCT { ?i <http://example.org/label> ?label }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/ids.csv,csv.headers=true> { ?r xyz:id ?id }
  BIND(IRI(CONCAT("x-sparql-anything:media-type=application/json,location=http://127.0.0.1:%PORT%/item/", ?id)) AS ?svc)
  SERVICE ?svc { ?o xyz:label ?label }
  BIND(IRI(CONCAT("http://example.org/item/", ?id)) AS ?i)
}""",
     "sa_note": "the facade holds the body of a response, not its headers"},
    {"name": "html-css", "what": "the elements of an HTML page selected by a CSS selector",
     "kind": "graph",
     "files": {"page.html": '<html><body><ul><li class="p">Ada</li><li class="q">x</li>'
                            '<li class="p">Bob</li></ul></body></html>\n'},
     "expected": """<http://example.org/doc> <http://example.org/person> "Ada" .
<http://example.org/doc> <http://example.org/person> "Bob" .
""",
     "sg": SG + """GENERATE { <doc> <person> ?t . }
ITERATOR iter:CSSPath(<page.html>, "li.p", "li/text()") AS ?li ?t""",
     "sa": SA + """CONSTRUCT { <http://example.org/doc> <http://example.org/person> ?t }
WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/page.html,html.selector=li.p> {
    ?li a <http://www.w3.org/1999/xhtml#li> ; rdf:_1 ?t . FILTER(isLiteral(?t))
  }
}"""},
    {"name": "mqtt", "what": "the messages of an MQTT topic for 60 s", "kind": "graph",
     "not_run": "needs an MQTT broker, and none runs on this machine",
     "sg_note": "iter:MQTTSubscribe", "sa_na": "no stream source"},
    {"name": "sql-table", "what": "the rows of a relational table", "kind": "graph",
     "not_run": "needs a database server, and none runs on this machine",
     "sg_note": "iter:SQL (JDBC; the MySQL driver is in the JAR)", "sa_na": "no relational source"},
    {"name": "exif", "what": "the EXIF metadata of an image", "kind": "graph",
     "not_run": "needs an image with EXIF metadata (no image library in this environment)",
     "sg_na": "no image metadata reader", "sa_note": "the Metadata triplifier"},
]
