#!/usr/bin/env node
// RDFC-1.0 (W3C RDF Dataset Canonicalization) of an N-Quads dataset, by rdf-canonize:
// blank nodes relabelled canonically (_:c14n0, ...), canonical N-Quads, sorted.
// Usage: node rdfc.js PACKAGE_DIR < in.nq > out.nq; PACKAGE_DIR the installed package
// (engines/rdfc-<version>/node_modules/rdf-canonize). In memory; the library's default
// limit on deep iterations is lifted. An error: "ERROR: ...", status 1.
const pkg = process.argv[2];
if (!pkg) {
  console.error('usage: rdfc.js PACKAGE_DIR < in.nq > out.nq');
  process.exit(2);
}
const canonize = require(require('path').resolve(pkg));
const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', () => {
  canonize
    .canonize(Buffer.concat(chunks).toString('utf8'), {
      algorithm: 'RDFC-1.0',
      inputFormat: 'application/n-quads',
      format: 'application/n-quads',
      // no limit on deep iterations: the harness bounds the process (time, memory)
      maxWorkFactor: Infinity,
    })
    .then((out) => process.stdout.write(out, () => process.exit(0)))
    .catch((err) => {
      console.error('ERROR: ' + (err && err.message ? err.message : err));
      process.exit(1);
    });
});
