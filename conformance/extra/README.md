# Extra test cases (kgc-bench)

Minimal cases written for the translator `rml2sparql-generate`, in the layout of the
RML-Core test cases (`metadata.csv`, one directory per case with `mapping.ttl`, its
inputs and the expected `output.nq`). Each reproduces one point that the official suites
do not test (the expected outputs of X004 to X006 are also those of RMLMapper 8.1.0):

| case | what |
|---|---|
| X001-CSV | a child subject map of term type BlankNode without expression, with a join to its parent: one blank node per child row, in the triples of the child and in the join triples |
| X002-CSV | a referencing object map over the same logical source, without join condition, the parent and the child with their own `rml:baseIRI`: the parent's subject resolved against the parent's base |
| X003-XML | XPath references to attributes of the iterated element (at most one value each, rewriting R6 of the translator: auxiliary queries of the iteration) next to a reference to a repeated element (two values) and an element without the attribute (no subject) |
| X004-CSV | graph maps in two triples maps of one CSV file (one shared iteration): a subject graph map with a template (the classes and every predicate-object map go to it), `rr:graph rr:defaultGraph` and a constant graph next to it, a predicate-object graph map with a reference |
| X005-CSV | graph maps with an expression on the child of joins: an IRI subject (the join made over the generated graphs) and a blank node subject without expression (the join made in the child's iteration), with a constant graph next to them |
| X006-JSON | a JSONPath graph map with two values, with none (an empty array, a missing key) next to a constant graph, which keeps its triples; a JSONPath join whose child has a graph map with a template |

`python -m harness.conformance --suites kgc-bench-extra --modes translated`
