#!/usr/bin/env python3
"""
RBP conformance verifier (reference).

Run the JCS canonicalization golden vectors through the reference
implementation and report PASS/FAIL per vector. Any other language
implementation should read fixtures/jcs-vectors.json, reproduce the
`canonical` string and `digest` for each `input`, and diff against these
golden values — a byte-for-byte match means the implementation is
canonicalization-conformant with RBP v0.1.

Usage:
    python3 fixtures/verify_fixtures.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import receipt  # noqa: E402


def verify_jcs_vectors(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    vectors = data.get("vectors", [])
    passed = 0
    failed = 0
    for v in vectors:
        got_canonical = receipt.canonical_json(v["input"])
        got_digest = receipt.canonical_digest(v["input"])
        ok = (got_canonical == v["canonical"]) and (got_digest == v["digest"])
        if ok:
            passed += 1
            print(f"  ✅ {v['id']}")
        else:
            failed += 1
            print(f"  ❌ {v['id']}")
            print(f"     canonical: expected {v['canonical']!r}")
            print(f"                got      {got_canonical!r}")
            print(f"     digest:    expected {v['digest']}")
            print(f"                got      {got_digest}")
    return passed, failed


def main():
    here = Path(__file__).resolve().parent
    print("RBP v0.1 conformance — JCS canonicalization vectors")
    passed, failed = verify_jcs_vectors(here / "jcs-vectors.json")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
