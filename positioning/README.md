# Positioning scenarios: SPARQL-Generate and SPARQL Anything

Executable checks of claims made when comparing SPARQL-Generate (SG) with SPARQL
Anything (SA). They measure correctness and behaviour, not time, so they can run on a
loaded machine. Results go to `results/` and to the "Positioning" sections of
`results/results.md`.

| Scenario | Question | Command | Result file |
|---|---|---|---|
| `slicing/` | Does the setting that makes large inputs fit in memory change the answers? SA `slice=true` and `slice.size`; SG iterators in batches | `python -m harness.slicing` | `results/slicing.csv` |
| `portability/` | SA queries parse as SPARQL 1.1: what do plain SPARQL engines answer? And SA itself, when an option is bound outside the `SERVICE` clause (issue #701)? | `python -m harness.portability` | `results/portability.csv` |
| `features/` | An executable feature matrix: RDF lists, text output, trees of unknown depth, joins of two formats, blank nodes per value, JSON Lines, YAML, XLSX, Markdown, CBOR, named graphs, HTTP headers, CSS selectors (MQTT, SQL and EXIF not run here) | `python -m harness.features` | `results/features.csv` |
| `fidelity/` | Are the values of the inputs read faithfully (large integers, decimals, null, empty containers, keys, XML mixed content, namespaces, CDATA, `xml:lang`, spaces, CSV quoting), and does it change from one release to the next? | `python -m harness.fidelity` | `results/fidelity.csv` |

Every engine process runs under the memory cap of the harness (see the main README).

## slicing

`make_data.py` writes 24 people as CSV, a top-level JSON array and XML (cities repeat,
managers refer to other rows, scores order them). `make_queries.py` writes the same 15
questions for the three formats (`queries/sa/<format>/`): plain patterns, joins of two
items (on the city, on the manager key, `FILTER EXISTS`), `COUNT`, `GROUP BY`,
`DISTINCT`, `ORDER BY ... LIMIT` and `MAX` inside the `SERVICE` clause, the neighbour
pattern with `fx:next`, the slots of the root container, and the same aggregates and
join outside the `SERVICE` clause. SA runs each with `slice=false` (the reference),
`slice=true`, and `slice.size` 2, 10 and 1000. The SG counterparts of the 10 questions
that do not depend on Facade-X containers (`queries/sg/`) run with `iter:CSV` and
`iter:JSONSurfer` in one batch (the reference) and in batches of 1, 2, 10 and 1000.

## portability

Eleven SA queries (`queries/`): SELECT over CSV, JSON and XML (with the magic property
`fx:anySlot`), an aggregate, a CONSTRUCT, `SERVICE SILENT`, the function `fx:entity`,
options as triples (`fxe:properties`), and the three queries of SA issue #701 (an option
bound to a variable inside the `SERVICE` clause, outside it by `BIND`, by `VALUES`). They
run on SA (the reference) and, on an empty dataset, on Apache Jena ARQ, rdflib, Oxigraph
(pyoxigraph), Comunica and SPARQL-Generate. Engines: `scripts/fetch_positioning.sh`,
versions in `versions.env`.

## fidelity

`cases.py`: one small input per case, the same question in SA and in SG, and the
faithful answer (a JSON integer is read as an integer, a decimal as `xsd:decimal`, an
exponent as `xsd:double`, `null` as no value; XML text with its spaces, its CDATA, its
namespace and its `xml:lang`; CSV cells with their line breaks and quotes). Every release
of `releases.txt` (SA 0.8.2 to 1.3.0, SG 2.0.9 to 2.2.2, fetched and checksummed by
`scripts/fetch_versions.sh` into `engines/versions/`) runs every case; the SG queries
are flat `BIND`s of `fun:JSONPath` and `fun:XPath` over a `SOURCE`, plus the streaming
`iter:JSONSurfer` and `iter:CSV`, so that every release reads them alike.

## features

`cases.py`: 17 minimal cases, each with its input, its expected output (N-Triples,
N-Quads or text), the SG query and the SA query, or the reason why one of them has no
construct for it, or why the case is not run here (an MQTT broker, a database server, an
image with EXIF metadata). A local HTTP server (HTTP/1.1, several connections) answers the
HTTP case. SA queries are written to give it its best chance (for instance a media type
for a URL without extension); the notes of `results.md` say what each failure comes from.
