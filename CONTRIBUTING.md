# Contributing to multi-agent-pipeline

Thanks for your interest in RBP (Receipt-Bearing Protocol). This is an open protocol for cross-vendor, verify-before-start agent handoffs, and we welcome contributions — fixes, new fixtures, spec clarifications, and ports to other languages.

## Ways to contribute

- **Report a bug or a negative example.** The protocol's value comes from its negative-example library (empty output, stale epoch, tampered digest, path traversal, …). If you hit a failure mode we haven't listed, open an issue.
- **Port the reference implementation.** `receipt.py` is the Python reference. A Rust/TypeScript/Go port that passes the same fixtures is a big win for cross-vendor conformance.
- **Fix or improve the reference implementation.** See the tests below for the invariants.
- **Improve the spec.** `RECEIPT-BEARING-PROTOCOL.md` is the source of truth; keep implementation and spec aligned.

## Development setup

Pure standard library, zero third-party dependencies for the protocol itself:

```bash
git clone git@github.com:dr-chai/multi-agent-pipeline.git
cd multi-agent-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install pytest
python -m pytest test_receipt.py -q
```

## Tests

`test_receipt.py` covers the fail-closed invariants:

- normal handoff → `(True, "OK")`
- tampered output → `(False, …)`
- expired epoch → `(False, …)`
- empty output → auto `REJECT`
- wrong source → `(False, "scope mismatch")`
- hollow receipt → `(False, "INCOMPLETE …")`

Add a test for every new negative example you contribute.

## Pull request checklist

- Run `python -m pytest test_receipt.py -q` and keep it green.
- Keep `receipt.py` pure standard library.
- If you change the schema or verification order, update `RECEIPT-BEARING-PROTOCOL.md` in the same PR.
- Follow the existing style (docstrings in the same spirit).

## License

MIT. By contributing you agree your work is licensed under the same terms.
