# RBP Conformance Fixtures

Language-agnostic test vectors for proving a Receipt-Bearing Protocol (RBP) implementation is conformant.

The one hard interop requirement is the **canonical digest**: every output is digested as `sha256(JCS(input))`, where JCS is RFC 8785 JSON Canonicalization Scheme. If two implementations produce the same digest for the same byte-level input, they can verify each other's receipts — that is the whole point of a cross-vendor protocol.

## `jcs-vectors.json`

Golden vectors. Each entry has:

- `input` — the JSON value to canonicalize
- `canonical` — the exact JCS canonical string (RFC 8785)
- `digest` — `sha256:<hex>` of the UTF-8 bytes of `canonical`

**A conformant implementation MUST reproduce `canonical` and `digest` byte-for-byte.** The vectors cover the tricky parts of JCS: key ordering, nested objects/arrays, Unicode escaping, string escaping, number formatting, null/boolean, and deep nesting.

## How to claim conformance in your language

1. Implement `canonical_json(value)` per RFC 8785 (sorted keys by UTF-16 code unit, no whitespace, standard escaping, integers only).
2. Implement `digest = "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()`.
3. Run your implementation against `jcs-vectors.json` and diff every `canonical` and `digest`.

All vectors pass ⇒ your implementation is canonicalization-conformant with RBP v0.1.

## Reference verifier

```bash
python3 fixtures/verify_fixtures.py
```

Runs the vectors through the reference implementation (`receipt.py`).

## Handoff semantics (fail-closed)

Digest conformance is necessary but not sufficient. A full implementation must also honour the verification order in `RECEIPT-BEARING-PROTOCOL.md` §7:

```
density → scope → digest → epoch → verdict
```

and fail closed on any check. The reference behaviour is covered by `test_receipt.py` (normal / tamper / stale / empty / wrong-source / hollow-receipt).
