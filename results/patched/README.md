# RML engines with proposed patches

Conformance of each RML engine as released (`released/`, the rows of
`results/conformance.csv`) and built with the patches of `scripts/patches/<engine>/`
(`patched/`; `patched-N/`: the first N patches only). Each patch fixes one
non-conformance to the RML specifications or to the test cases of the W3C KG-Construct CG,
with tests in the engine's own suite, and is written to be proposed upstream; none is
published by this repository. These are never the scores of a release.

Rule: the published one (an empty output counts as an error reported for a case that
expects an error). Suites: those pinned in `versions.env`. Measured on 2026-11-26/27 with
`scripts/patches/measure.sh`; table by `python scripts/patches/summary.py`.

| engine | base of the patches | patches (scripts/patches/<engine>/) |
|---|---|---|
| Morph-KGC | main 979ade7 (2.10.0 + unreleased commits) | relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates |
| SDM-RDFizer | master b8c71fd (4.7.5.15.4.1) | base-iri, join-term-maps (fixed upstream, unreleased: for measurement only), postgres-port |
| RPT | R2-RML-Toolkit develop b640973, classes compiled against the 2.0.0-rc7 jar | blank-node-sources, language-map, uri-term-type |
| RMLMapper | development 86e961d7 (8.1.0 + #270) | natural-datatypes-json |
| FlexRML | 3.1.0 | no-natural-datatype-for-csv-xml, fno-parameter-iri |
| BURP | main 906bb5a (0.1.3) | fno-parameter-iri |
| RocketRML | 3.0.0 (npm package, src/ hunks) | join-empty-values, join-duplicates |
| RMLStreamer | development 1f4dbad (2.5.0 + two cosmetic commits) | graph-map-union (measured on rml-test-cases only: it does not read the CG vocabulary) |

`rocketrml/gtfs/perf.csv`: GTFS-Madrid-Bench scale 1 with both RocketRML patches (10 s, 0.8 GB,
395,953 triples; the fingerprint differs from the reference only by the canonical lexical form
that jsonld.toRDF gives to the 180,508 xsd:double literals).

| engine | variant | version | rml-test-cases | rml-core | rml-io | rml-fnml | rml-cc | rml-star | rml-lv | total |
|---|---|---|---|---|---|---|---|---|---|---|
| burp | patched | BURP 0.1.3+patched [patches: fno-parameter-iri] | 24/117 | 76/76 | 68/73 | 21/22 | 35/35 | 1/18 | 41/41 | 266 |
| burp | released | BURP 0.1.3 | 24/117 | 76/76 | 68/73 | 17/22 | 35/35 | 1/18 | 41/41 | 262 |
| flexrml | patched-1 | FlexRML 3.1.0+patched [patches: no-natural-datatype-for-csv-xml] | 111/117 | 76/76 | 17/73 | 17/22 | 0/35 | 0/18 | 10/41 | 231 |
| flexrml | patched | FlexRML 3.1.0+patched [patches: no-natural-datatype-for-csv-xml, fno-parameter-iri] | 111/117 | 76/76 | 17/73 | 21/22 | 0/35 | 0/18 | 10/41 | 235 |
| flexrml | released | FlexRML 3.1.0 | 84/117 | 76/76 | 11/73 | 17/22 | 0/35 | 0/18 | 10/41 | 198 |
| morph-kgc | patched-1 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source] | 97/117 | 36/76 | 8/73 | 5/22 | 0/35 | 2/18 | 10/41 | 158 |
| morph-kgc | patched-2 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes] | 97/117 | 45/76 | 14/73 | 5/22 | 0/35 | 2/18 | 10/41 | 173 |
| morph-kgc | patched-3 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri] | 103/117 | 52/76 | 14/73 | 5/22 | 0/35 | 2/18 | 10/41 | 186 |
| morph-kgc | patched | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates] | 103/117 | 52/76 | 14/73 | 12/22 | 0/35 | 2/18 | 10/41 | 193 |
| morph-kgc | released | Morph-KGC 2.10.0 | 97/117 | 16/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 132 |
| rmlmapper | patched | RMLMapper development-86e961d7+patched [patches: natural-datatypes-json] | 117/117 | 59/76 | 51/73 | 6/22 | 0/35 | 0/18 | 10/41 | 243 |
| rmlmapper | released | RMLMapper 8.1.0 | 117/117 | 42/76 | 16/73 | 6/22 | 0/35 | 0/18 | 10/41 | 191 |
| rmlstreamer | patched | RMLStreamer 2.5.0+patched [patches: graph-map-union] | 117/117 | — | — | — | — | — | — | 117 |
| rmlstreamer | released | RMLStreamer 2.5.0 | 114/117 | 16/76 | 2/73 | 6/22 | 0/35 | 2/18 | 10/41 | 150 |
| rocketrml | patched-1 | RocketRML 3.0.0+patched [patches: join-empty-values] | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 |
| rocketrml | patched | RocketRML 3.0.0+patched [patches: join-empty-values, join-duplicates] | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 |
| rocketrml | released | RocketRML 3.0.0 | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 |
| rpt | patched | RPT 2.0.0-rc7+patched [patches: blank-node-sources, language-map, uri-term-type] | 91/117 | 51/76 | 15/73 | 5/22 | 0/35 | 2/18 | 10/41 | 174 |
| rpt | released | RPT 2.0.0-rc7 | 91/117 | 16/76 | 5/73 | 5/22 | 0/35 | 2/18 | 10/41 | 129 |
| sdm-rdfizer | patched-2 | SDM-RDFizer 4.7.5.15.4.1 [patches: base-iri, join-term-maps] | 76/117 | 71/76 | 64/73 | 17/22 | 34/35 | 18/18 | 39/41 | 319 |
| sdm-rdfizer | patched | SDM-RDFizer 4.7.5.15.4.1 [patches: base-iri, join-term-maps, postgres-port] | 76/117 | 71/76 | 65/73 | 17/22 | 34/35 | 18/18 | 39/41 | 320 |
| sdm-rdfizer | released | SDM-RDFizer 4.7.5.15.4.1 | 76/117 | 63/76 | 65/73 | 17/22 | 34/35 | 18/18 | 39/41 | 312 |
