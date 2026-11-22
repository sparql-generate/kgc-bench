"""The fidelity cases (positioning, argument 9): one small input per case, the
same question asked in SPARQL Anything (sa) and SPARQL-Generate (sg), and the
faithful answer. A query returns pairs (?k, ?v), a key (the role of the value)
and the value read; or one column ?v1 ... ?vn per key of "sg_keys" (the
SPARQL-Generate queries: flat BINDs, the form every release reads alike).

expected maps each key to the faithful value: a str for a literal of that
lexical form, a tuple (lexical, datatype) to check the datatype too, a set of
strings for several values, or None for "no value" (JSON null).
%DATA% is the directory of the inputs.
"""

XSD = "http://www.w3.org/2001/XMLSchema#"

SA_PREFIXES = """PREFIX xyz: <http://sparql.xyz/facade-x/data/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""
SG_PREFIXES = """PREFIX iter: <http://w3id.org/sparql-generate/iter/>
PREFIX fun:  <http://w3id.org/sparql-generate/fn/>
"""


def sa_json_keys(f):
    """Every key of the top-level JSON object and its value."""
    return SA_PREFIXES + """SELECT ?k ?v WHERE {
  SERVICE <x-sparql-anything:location=%%DATA%%/%s> {
    ?s ?p ?v . FILTER(STRSTARTS(STR(?p), STR(xyz:)))
  }
  BIND(STRAFTER(STR(?p), STR(xyz:)) AS ?k)
}""" % f


def sg_json_keys(f, keys):
    binds = "\n".join("  BIND(fun:JSONPath(?doc, \"$['%s']\") AS ?v%d)" % (k, i + 1)
                      for i, k in enumerate(keys))
    return SG_PREFIXES + "SELECT %s\nSOURCE <%s> AS ?doc\nWHERE {\n%s\n}" % (
        " ".join("?v%d" % (i + 1) for i in range(len(keys))), f, binds)


def sa_xml_literals(f, k="text"):
    """Every literal of the XML facade (text nodes, attributes)."""
    return SA_PREFIXES + """SELECT ?k ?v WHERE {
  SERVICE <x-sparql-anything:location=%%DATA%%/%s> { ?s ?p ?v . FILTER(isLiteral(?v)) }
  BIND("%s" AS ?k)
}""" % (f, k)


def sg_xpath(f, exprs):
    """One XPath expression per key, on the document."""
    binds = "\n".join('  BIND(fun:XPath(?doc, "%s") AS ?v%d)' % (e, i + 1) for i, e in enumerate(exprs))
    return SG_PREFIXES + "SELECT %s\nSOURCE <%s> AS ?doc\nWHERE {\n%s\n}" % (
        " ".join("?v%d" % (i + 1) for i in range(len(exprs))), f, binds)


NUMBERS = '{"big": 9223372036854775808, "int": 42, "neg": -7, "dec": 0.1, "exp": 1.5e300, "zero": 0.0}\n'

CASES = [
    {"name": "json-numbers", "file": "numbers.json", "data": NUMBERS,
     "what": "JSON numbers: an integer above 2^63, small integers, a decimal, an exponent",
     "sa": sa_json_keys("numbers.json"),
     "sg": sg_json_keys("numbers.json", ["big", "int", "neg", "dec", "exp", "zero"]),
     "sg_keys": ["big", "int", "neg", "dec", "exp", "zero"],
     "expected": {"big": ("9223372036854775808", "integer"), "int": ("42", "integer"),
                  "neg": ("-7", "integer"), "dec": ("0.1", "decimal"),
                  "exp": ("1.5E300", "double"), "zero": ("0.0", "decimal")}},
    {"name": "json-numbers-stream", "file": "numbers.json", "data": NUMBERS,
     "what": "the same numbers, read by the streaming JSON iterator of SPARQL-Generate",
     "sa": None,
     "sg": SG_PREFIXES + """SELECT ?v1 ?v2 ?v3 ?v4 ?v5 ?v6
ITERATOR iter:JSONSurfer(<numbers.json>, "$", "$.big", "$.int", "$.neg", "$.dec", "$.exp", "$.zero")
    AS ?o ?v1 ?v2 ?v3 ?v4 ?v5 ?v6
WHERE { }""",
     "sg_keys": ["big", "int", "neg", "dec", "exp", "zero"],
     "expected": {"big": ("9223372036854775808", "integer"), "int": ("42", "integer"),
                  "neg": ("-7", "integer"), "dec": ("0.1", "decimal"),
                  "exp": ("1.5E300", "double"), "zero": ("0.0", "decimal")}},
    {"name": "json-null-empty", "file": "null.json",
     "data": '{"n": null, "s": "", "arr": [], "obj": {}, "t": true}\n',
     "what": "JSON null (no value), the empty string, empty containers, a boolean",
     "sa": sa_json_keys("null.json"),
     "sg": sg_json_keys("null.json", ["n", "s", "arr", "obj", "t"]),
     "sg_keys": ["n", "s", "arr", "obj", "t"],
     "expected": {"n": None, "s": "", "arr": "*", "obj": "*", "t": ("true", "boolean")}},
    {"name": "json-keys", "file": "keys.json",
     "data": '{"clé été": 1, "a b": 2, "dup": 1, "dup": 2, "日本": 3}\n',
     "what": "keys with spaces and non-ASCII characters; a duplicate key (RFC 8259 leaves it open: recorded, not judged)",
     "sa": sa_json_keys("keys.json"),
     "sg": sg_json_keys("keys.json", ["clé été", "a b", "dup", "日本"]),
     "sg_keys": ["clé été", "a b", "dup", "日本"],
     "expected": {"clé été": "1", "a b": "2", "dup": "*", "日本": "3"}},
    {"name": "xml-mixed", "file": "mixed.xml", "data": "<p>Hello <b>World</b>!</p>\n",
     "what": "XML mixed content: the text around and inside an element, spaces kept",
     "sa": sa_xml_literals("mixed.xml"),
     "sg": SG_PREFIXES + """SELECT ?k ?v
ITERATOR iter:XPath(<mixed.xml>, "/p//text()") AS ?t
WHERE { BIND("text" AS ?k) BIND(STR(?t) AS ?v) }""",
     "expected": {"text": {"Hello ", "World", "!"}}},
    {"name": "xml-namespace", "file": "ns.xml",
     "data": '<r xmlns:x="http://example.org/x#"><x:item>1</x:item></r>\n',
     "what": "the namespace of an XML element",
     "sa": SA_PREFIXES + """SELECT ?k ?v WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/ns.xml> { ?e a ?type ; rdf:_1 "1" }
  BIND("element" AS ?k) BIND(STR(?type) AS ?v)
}""",
     "sg": sg_xpath("ns.xml", ["concat(namespace-uri(/r/*[1]), local-name(/r/*[1]))"]),
     "sg_keys": ["element"],
     "expected": {"element": "http://example.org/x#item"}},
    {"name": "xml-cdata", "file": "cdata.xml", "data": "<r><![CDATA[<x> & y]]></r>\n",
     "what": "a CDATA section",
     "sa": sa_xml_literals("cdata.xml"),
     "sg": sg_xpath("cdata.xml", ["string(/r)"]),
     "sg_keys": ["text"],
     "expected": {"text": "<x> & y"}},
    {"name": "xml-lang", "file": "lang.xml", "data": '<r xml:lang="fr">bonjour</r>\n',
     "what": "xml:lang: the language of the text",
     "sa": SA_PREFIXES + """SELECT ?k ?v WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/lang.xml> { ?s rdf:_1 ?t . FILTER(isLiteral(?t)) }
  BIND("lang" AS ?k) BIND(LANG(?t) AS ?v)
}""",
     "sg": sg_xpath("lang.xml", ["string(/r/@xml:lang)"]),
     "sg_keys": ["lang"],
     "expected": {"lang": "fr"}},
    {"name": "xml-space", "file": "space.xml", "data": "<r>  two  spaces  </r>\n",
     "what": "leading, trailing and inner spaces of an XML text",
     "sa": sa_xml_literals("space.xml"),
     "sg": sg_xpath("space.xml", ["string(/r)"]),
     "sg_keys": ["text"],
     "expected": {"text": "  two  spaces  "}},
    {"name": "csv-quoted", "file": "quoted.csv",
     "data": 'id,text\n1,"line one\nline two"\n2,"a ""quoted"" word"\n3,\n',
     "what": "CSV: a line break and quotes inside a quoted cell, an empty cell",
     "sa": SA_PREFIXES + """SELECT ?k ?v WHERE {
  SERVICE <x-sparql-anything:location=%DATA%/quoted.csv,csv.headers=true> { ?r xyz:id ?k ; xyz:text ?v }
}""",
     "sg": SG_PREFIXES + """SELECT ?k ?v
ITERATOR iter:CSV(<quoted.csv>) AS ?k ?v
WHERE { }""",
     "expected": {"1": "line one\nline two", "2": 'a "quoted" word', "3": None}},
]
