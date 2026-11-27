# Extra test cases (kgc-bench)

Minimal cases written for the translator `rml2sparql-generate`, in the layout of the
RML-Core test cases (`metadata.csv`, one directory per case with `mapping.ttl`, its
inputs and the expected `output.nq`). Each reproduces one point that the official suites
do not test (the expected outputs of X004 to X007 and X009 are also those of RMLMapper 8.1.0):

| case | what |
|---|---|
| X001-CSV | a child subject map of term type BlankNode without expression, with a join to its parent: one blank node per child row, in the triples of the child and in the join triples |
| X002-CSV | a referencing object map over the same logical source, without join condition, the parent and the child with their own `rml:baseIRI`: the parent's subject resolved against the parent's base |
| X003-XML | XPath references to attributes of the iterated element (at most one value each, rewriting R6 of the translator: auxiliary queries of the iteration) next to a reference to a repeated element (two values) and an element without the attribute (no subject) |
| X004-CSV | graph maps in two triples maps of one CSV file (one shared iteration): a subject graph map with a template (the classes and every predicate-object map go to it), `rr:graph rr:defaultGraph` and a constant graph next to it, a predicate-object graph map with a reference |
| X005-CSV | graph maps with an expression on the child of joins: an IRI subject (the join made over the generated graphs) and a blank node subject without expression (the join made in the child's iteration), with a constant graph next to them |
| X006-JSON | a JSONPath graph map with two values, with none (an empty array, a missing key) next to a constant graph, which keeps its triples; a JSONPath join whose child has a graph map with a template |
| X007-CSV | joins of a CSV file with itself (RML 1.x, separate logical sources with the same description): on one column, whose child subject depends on that column only (`shape/{shape_id}`, `kind/{kind}`: made on the same row, rewriting R8 of the translator), several rows per value; and joins that must not be rewritten, a child subject with another column (`row/{shape_id}-{seq}`: every row of the same value) and a parent in another file; empty cells in the join column and in the parent subject |
| X008-CSV | RML-Core: joins of a CSV file with itself, logical sources of the same description (blank node sources: made on the same row, rewriting R8) or not (`rml:null` on the parent's source: two readings of the file, and no shared iteration, rewriting R3); the expected output written by hand from RML-IO, RMLMapper 8.1.0 not reading `rml:null` |
| X009-CSV | joins of two CSV files on one column whose parent subject depends on that column only (a reference, `route_id`: the child read as a stream, rewriting R9) or not (`routeName/{route_id}-{name}`): a parent key on two rows, an empty child key (no join, and not with every parent), a child key without parent, an empty parent key, a child subject shared by two rows |

`python -m harness.conformance --suites kgc-bench-extra --modes translated`
