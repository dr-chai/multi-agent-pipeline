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

## Reference implementations

Two independent implementations reproduce all 7 vectors (7/7):

```bash
# Python reference
python3 fixtures/verify_fixtures.py

# TypeScript reference (Node.js >= 23, native type-stripping)
node fixtures/verify_ts.mjs
```

| Implementation | File |
|---|---|
| Python | `receipt.py` |
| TypeScript (Node.js) | `receipt.ts` |

## Number precision note

The `numbers` vector's `big` field is `9007199254740991` (2^53−1), the largest integer exactly representable as an IEEE-754 double — the precision every mainstream JSON parser uses. Integers beyond 2^53 are **not** portable: Python's `json` preserves them, but JavaScript's `JSON.parse` (and most languages) rounds them. RBP v0.1 therefore bounds canonical-digest inputs to IEEE-754-safe integers; larger integers must be carried as strings.

## Handoff semantics (fail-closed)

Digest conformance is necessary but not sufficient. A full implementation must also honour the verification order in `RECEIPT-BEARING-PROTOCOL.md` §7:

```
density → scope → digest → epoch → verdict
```

and fail closed on any check. The reference behaviour is covered by `test_receipt.py` (normal / tamper / stale / empty / wrong-source / hollow-receipt).

## `9-19-fixture.md` — 9/19 五方預檢對拍

Higher-level handoff fixtures for the **9/19 five-party pre-check window**: `input_digest` + `tool_call_sequence` field names, transient-vs-hard boundary (HOLD vs REJECT), receipt 重發 vs 新工作 (idempotency_key), and 8 negative fixtures with scriptable expected verdicts. See `fixtures/9-19-fixture.md`.
