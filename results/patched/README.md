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
| Morph-KGC | main 979ade7 (2.10.0 + unreleased commits) | relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates, json-bracket-references, uri-term-type, constant-literal-annotations, join-term-maps |
| SDM-RDFizer | master b8c71fd (4.7.5.15.4.1) | base-iri, join-term-maps (fixed upstream, unreleased: for measurement only), postgres-port, natural-datatypes, language-map-reference |
| RPT | R2-RML-Toolkit develop b640973, classes compiled against the 2.0.0-rc7 jar | blank-node-sources, language-map, uri-term-type, join-term-maps |
| RMLMapper | development 86e961d7 (8.1.0 + #270) | natural-datatypes-json, json-bracket-references, target-compression, join-term-maps |
| FlexRML | 3.1.0 | no-natural-datatype-for-csv-xml, fno-parameter-iri |
| BURP | main 906bb5a (0.1.3) | fno-parameter-iri, target-compression |
| RocketRML | 3.0.0 (npm package, src/ hunks) | join-empty-values, join-duplicates, double-lexical-form, stream-nquads, graph-maps, multiple-classes |
| RMLStreamer | development 1f4dbad (2.5.0 + two cosmetic commits) | graph-map-union (measured on rml-test-cases only: it does not read the CG vocabulary) |

`rocketrml/gtfs/perf.csv`: GTFS-Madrid-Bench with the RocketRML patches, output checked by
fingerprint against Morph-KGC: scale 1 (all six patches) 7 s, 0.6 GB; scale 10 (the first four)
105 s, 4.2 GB; both outputs equal to the reference.

**SQL tracks** of rml-test-cases (suite `rml-test-cases-sql`, columns `sql …`, outside the
total) and RMLSTC0006a, measured 2026-11-27 on the default ports (one server per kind at a
time, `harness.database`); `released/` holds the rows of `results/conformance.csv`. No patch
changes a score on them, but for Morph-KGC:

- SDM-RDFizer, RMLMapper, BURP, RMLStreamer: the same statuses as the release, case by case.
  `postgres-port` of SDM-RDFizer has no effect on the default port (it matters on another).
  BURP reads the SQL source of the CG vocabulary (RMLSTC0006a passes) but not the legacy
  vocabulary of these tracks: its 14 PASS are cases that expect an error. RMLStreamer times
  out (120 s) on most cases, released or patched;
- Morph-KGC: RMLTC0019a and RMLTC0020a pass on the three tracks with `base-iri` (0020a-PostgreSQL
  excepted), and RMLTC0009a-b (a referencing object map between two tables) fail. The latter is
  a regression of `main` 979ade7 itself, without any patch, not of the patches (each prefix of
  the patch stack, checked on MySQL); 2.10.0 passes them. The patched installation needs
  SQLAlchemy >= 2.0.42 for its pandas 3 (`scripts/patches/build.sh`);
- FlexRML, RocketRML, RPT: no SQL source, released or patched ("No logical source path
  found", "SQL2008Table not supported", RPT's "No resource manager configured for query execution"); their PASS are
  cases that expect an error.

| engine | variant | version | rml-test-cases | rml-core | rml-io | rml-fnml | rml-cc | rml-star | rml-lv | total | sql PostgreSQL | sql MySQL | sql SQLServer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| burp | patched-1 | BURP 0.1.3+patched [patches: fno-parameter-iri] | 24/117 | 76/76 | 68/73 | 21/22 | 35/35 | 1/18 | 41/41 | 266 | — | — | — |
| burp | patched | BURP 0.1.3+patched [patches: fno-parameter-iri, target-compression] | 24/117 | 76/76 | 73/73 | 21/22 | 35/35 | 1/18 | 41/41 | 271 | 14/60 | 14/60 | 14/60 |
| burp | released | BURP 0.1.3 | 24/117 | 76/76 | 68/73 | 17/22 | 35/35 | 1/18 | 41/41 | 262 | 14/60 | 14/60 | 14/60 |
| flexrml | patched-1 | FlexRML 3.1.0+patched [patches: no-natural-datatype-for-csv-xml] | 111/117 | 76/76 | 17/73 | 17/22 | 0/35 | 0/18 | 10/41 | 231 | — | — | — |
| flexrml | patched | FlexRML 3.1.0+patched [patches: no-natural-datatype-for-csv-xml, fno-parameter-iri] | 111/117 | 76/76 | 17/73 | 21/22 | 0/35 | 0/18 | 10/41 | 235 | 10/60 | 10/60 | 10/60 |
| flexrml | released | FlexRML 3.1.0 | 84/117 | 76/76 | 11/73 | 17/22 | 0/35 | 0/18 | 10/41 | 198 | 10/60 | 10/60 | 10/60 |
| morph-kgc | patched-1 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source] | 97/117 | 36/76 | 8/73 | 5/22 | 0/35 | 2/18 | 10/41 | 158 | — | — | — |
| morph-kgc | patched-2 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes] | 97/117 | 45/76 | 14/73 | 5/22 | 0/35 | 2/18 | 10/41 | 173 | — | — | — |
| morph-kgc | patched-3 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri] | 103/117 | 52/76 | 14/73 | 5/22 | 0/35 | 2/18 | 10/41 | 186 | — | — | — |
| morph-kgc | patched-4 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates] | 103/117 | 52/76 | 14/73 | 12/22 | 0/35 | 2/18 | 10/41 | 193 | — | — | — |
| morph-kgc | patched-7 | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates, json-bracket-references, uri-term-type, constant-literal-annotations] | 103/117 | 58/76 | 14/73 | 12/22 | 0/35 | 2/18 | 10/41 | 199 | — | — | — |
| morph-kgc | patched | Morph-KGC 2.10.0 [patches: main 979ade7, relative-path-source, json-natural-datatypes, base-iri, fno-parameter-predicates, json-bracket-references, uri-term-type, constant-literal-annotations, join-term-maps] | 103/117 | 64/76 | 14/73 | 12/22 | 0/35 | 2/18 | 10/41 | 205 | 29/60 | 29/60 | 29/60 |
| morph-kgc | released | Morph-KGC 2.10.0 | 97/117 | 16/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 132 | 30/60 | 29/60 | 29/60 |
| rmlmapper | patched-1 | RMLMapper development-86e961d7+patched [patches: natural-datatypes-json] | 117/117 | 59/76 | 51/73 | 6/22 | 0/35 | 0/18 | 10/41 | 243 | — | — | — |
| rmlmapper | patched-2 | RMLMapper development-86e961d7+patched [patches: natural-datatypes-json, json-bracket-references] | 117/117 | 62/76 | 51/73 | 6/22 | 0/35 | 0/18 | 10/41 | 246 | — | — | — |
| rmlmapper | patched-3 | RMLMapper development-86e961d7+patched [patches: natural-datatypes-json, json-bracket-references, target-compression] | 117/117 | 62/76 | 52/73 | 6/22 | 0/35 | 0/18 | 10/41 | 247 | — | — | — |
| rmlmapper | patched | RMLMapper development-86e961d7+patched [patches: natural-datatypes-json, json-bracket-references, target-compression, join-term-maps] | 117/117 | 68/76 | 52/73 | 6/22 | 0/35 | 0/18 | 10/41 | 253 | 54/60 | 55/60 | 56/60 |
| rmlmapper | released | RMLMapper 8.1.0 | 117/117 | 42/76 | 16/73 | 6/22 | 0/35 | 0/18 | 10/41 | 191 | 54/60 | 55/60 | 56/60 |
| rmlstreamer | patched | RMLStreamer 2.5.0+patched [patches: graph-map-union] | 117/117 | — | 0/1 | — | — | — | — | 117 | 12/60 | 10/60 | 10/60 |
| rmlstreamer | released | RMLStreamer 2.5.0 | 114/117 | 16/76 | 2/73 | 6/22 | 0/35 | 2/18 | 10/41 | 150 | 12/60 | 10/60 | 10/60 |
| rocketrml | patched-1 | RocketRML 3.0.0+patched [patches: join-empty-values] | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 | — | — | — |
| rocketrml | patched-2 | RocketRML 3.0.0+patched [patches: join-empty-values, join-duplicates] | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 | — | — | — |
| rocketrml | patched-3 | RocketRML 3.0.0+patched [patches: join-empty-values, join-duplicates, double-lexical-form] | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 | — | — | — |
| rocketrml | patched | RocketRML 3.0.0+patched [patches: join-empty-values, join-duplicates, double-lexical-form, stream-nquads, graph-maps, multiple-classes] | 114/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 148 | 10/60 | 10/60 | 10/60 |
| rocketrml | released | RocketRML 3.0.0 | 93/117 | 15/76 | 2/73 | 5/22 | 0/35 | 2/18 | 10/41 | 127 | 10/60 | 10/60 | 10/60 |
| rpt | patched-3 | RPT 2.0.0-rc7+patched [patches: blank-node-sources, language-map, uri-term-type] | 91/117 | 51/76 | 15/73 | 5/22 | 0/35 | 2/18 | 10/41 | 174 | — | — | — |
| rpt | patched | RPT 2.0.0-rc7+patched [patches: blank-node-sources, language-map, uri-term-type, join-term-maps] | 91/117 | 57/76 | 15/73 | 5/22 | 0/35 | 2/18 | 10/41 | 180 | 10/60 | 10/60 | 10/60 |
| rpt | released | RPT 2.0.0-rc7 | 91/117 | 16/76 | 5/73 | 5/22 | 0/35 | 2/18 | 10/41 | 129 | 10/60 | 10/60 | 10/60 |
| sdm-rdfizer | patched-2 | SDM-RDFizer 4.7.5.15.4.1 [patches: base-iri, join-term-maps] | 76/117 | 71/76 | 64/73 | 17/22 | 34/35 | 18/18 | 39/41 | 319 | — | — | — |
| sdm-rdfizer | patched-3 | SDM-RDFizer 4.7.5.15.4.1 [patches: base-iri, join-term-maps, postgres-port] | 76/117 | 71/76 | 65/73 | 17/22 | 34/35 | 18/18 | 39/41 | 320 | — | — | — |
| sdm-rdfizer | patched | SDM-RDFizer 4.7.5.15.4.1 [patches: base-iri, join-term-maps, postgres-port, natural-datatypes, language-map-reference] | 88/117 | 72/76 | 67/73 | 17/22 | 34/35 | 18/18 | 39/41 | 335 | 30/60 | 32/60 | 15/60 |
| sdm-rdfizer | released | SDM-RDFizer 4.7.5.15.4.1 | 76/117 | 63/76 | 65/73 | 17/22 | 34/35 | 18/18 | 39/41 | 312 | 30/60 | 32/60 | 15/60 |
