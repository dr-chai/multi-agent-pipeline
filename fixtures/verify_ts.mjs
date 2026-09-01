// RBP conformance verifier (TypeScript / Node.js).
//
// Runs the JCS golden vectors through the TypeScript reference
// implementation (../receipt.ts) and diffs against the golden values.
// Requires Node.js >= 23 (native TypeScript type-stripping).
//
// Usage: node fixtures/verify_ts.mjs

import { canonicalJson, canonicalDigest } from '../receipt.ts';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, 'jcs-vectors.json'), 'utf8'));

let pass = 0;
let fail = 0;
for (const v of data.vectors) {
  const gotCanonical = canonicalJson(v.input);
  const gotDigest = canonicalDigest(v.input);
  const ok = gotCanonical === v.canonical && gotDigest === v.digest;
  if (ok) {
    pass += 1;
    console.log('  ✅ ' + v.id);
  } else {
    fail += 1;
    console.log('  ❌ ' + v.id);
    console.log('     expected canonical: ' + v.canonical);
    console.log('     got      canonical: ' + gotCanonical);
    console.log('     expected digest: ' + v.digest);
    console.log('     got      digest: ' + gotDigest);
  }
}
console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail === 0 ? 0 : 1);
