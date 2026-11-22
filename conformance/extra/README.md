# Extra test cases (kgc-bench)

Minimal cases written for the translator `rml2sparql-generate`, in the layout of the
RML-Core test cases (`metadata.csv`, one directory per case with `mapping.ttl`, its
inputs and the expected `output.nq`). Each reproduces one point that the official suites
do not test:

| case | what |
|---|---|
| X001-CSV | a child subject map of term type BlankNode without expression, with a join to its parent: one blank node per child row, in the triples of the child and in the join triples |
| X002-CSV | a referencing object map over the same logical source, without join condition, the parent and the child with their own `rml:baseIRI`: the parent's subject resolved against the parent's base |
| X003-XML | XPath references to attributes of the iterated element (at most one value each, rewriting R6 of the translator: auxiliary queries of the iteration) next to a reference to a repeated element (two values) and an element without the attribute (no subject) |

`python -m harness.conformance --suites kgc-bench-extra --modes translated`
