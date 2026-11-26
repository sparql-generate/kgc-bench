#!/usr/bin/env node
// RocketRML has no command line: this runs parseFile, as its README shows, with
// N-Quads output (toRDF). Usage: node rocketrml.js PACKAGE_DIR MAPPING OUTPUT, PACKAGE_DIR
// the installed package (engines/rocketrml-<version>/node_modules/rocketrml).
// An error is printed as "ERROR: ..." and exits with status 1.
const [pkg, mapping, output] = process.argv.slice(2);
if (!pkg || !mapping || !output) {
  console.error('usage: rocketrml.js PACKAGE_DIR MAPPING OUTPUT');
  process.exit(2);
}
const parser = require(require('path').resolve(pkg));
parser
  .parseFile(mapping, output, { toRDF: true, verbose: false })
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('ERROR: ' + (err && err.stack ? err.stack : err));
    process.exit(1);
  });
