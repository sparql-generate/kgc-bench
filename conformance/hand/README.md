# Hand-written SPARQL-Generate solutions of the RML test cases

One query per test case, `<suite>/<case id>.rqg`, written as a SPARQL-Generate
user would write it after reading the case's mapping — not generated. The
harness (`python -m harness.conformance --modes hand`) copies the case's input
documents next to the query and runs it with `-b <base>`, so that a query
names its sources relatively (`SOURCE <student.csv>`, `iter:CSV(<student.csv>)`).

Idioms used throughout, and why:

| RML feature | SPARQL-Generate idiom |
|---|---|
| logical source, `ql:CSV` | `ITERATOR iter:CSV(<f.csv>, "col", ...) AS ?col ...` (an empty cell is unbound) |
| `ql:JSONPath` | `ITERATOR iter:JSONPath(<f.json>, "$.it[*]", "$.ref", ...) AS ?rec ?ref ...`; numbers come back typed, `STR()` gives the RML lexical form |
| `ql:XPath` | `ITERATOR iter:XPath(<f.xml>, "/root/rec", "/rec/ref/text()", ...) AS ?rec ?ref ...` (2.2.0; the iterator of 2.1.0 lower-cases element names) |
| `rr:template` (IRI) | `<http://ex/{?v}>`: an expression inside an IRI of a GENERATE template is percent-encoded by the engine (`ENCODE_FOR_URI`, which is the IRI-safe encoding on ASCII); a JSON number needs `{STR(?v)}`, or the triple is silently dropped. In TEMPLATE text, `ENCODE_FOR_URI` is explicit |
| blank node from a value | `_:b` is fresh per solution: rows are grouped by the key first (`GROUP BY`), one solution per blank node; to share it with a nested GENERATE, bind it (`EXPRESSIONS (BNODE() AS ?b)`) and pass the variable: a template `_:b` is not shared with nested queries |
| named graphs | a GENERATE template holds triples only: the query is a TEMPLATE writing N-Quads |
| relative IRI (`rml:reference`, term type IRI) | `IRI(CONCAT(base, ?v))` when `?v` has no scheme: RML concatenates, while `IRI(?v)` would resolve and remove dot segments; an invalid IRI makes `IRI()` fail, and the triple is dropped |
| join (`rr:joinCondition`) | the parent's keys are generated into the default graph (`FROM GENERATE`), the join is a SPARQL graph pattern; an unbound child key is replaced by an IRI so that it matches nothing |
