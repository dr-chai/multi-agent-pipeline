# Receipt-Bearing Protocol (RBP) — Verified Handoff for Multi-Agent Collaboration

> Not a mailbox — a **handoff contract**. Verify before you start, fail-closed.
>
> Full protocol spec: [RECEIPT-BEARING-PROTOCOL.md](./RECEIPT-BEARING-PROTOCOL.md)

## Core idea

RBP is a **cross-vendor handoff-verification protocol**. When an agent finishes its work, it writes a **receipt** (a handoff credential). The downstream agent **verifies before it starts**; any failed check means **fail-closed** — it does not start.

The market's weakest link in multi-agent systems isn't any single agent — it's the **handoff point between agents**. RBP fixes that gap, on top of existing protocols (A2A/MCP handle discovery and transport; RBP handles the "did you actually finish, and is this the right version?" question).

### Three layers of guarantee

| Layer | Field | What it guarantees |
|---|---|---|
| Freshness | `epoch` | Reject stale state: `now - epoch <= max_age` (and no future timestamps) |
| Integrity | `content_digest` / `canonical_digest` | Detect tampering; downstream recomputes the hashes |
| Decision | `typed_reason` | Typed reason for why this step is in this state; anything but `PASS` fails closed |

### Fail-closed

Any verification failure = do not start. Empty output (0 bytes) is automatically downgraded to `REJECT` — silence is never treated as success.

## Install

Pure standard library, zero third-party dependencies:

```bash
# Requires Python 3.8+
python3 -c "import receipt; print('OK')"
```

Dependencies: `hashlib`, `json`, `re`, `time`, `pathlib` (all standard library).

## Quick start

```python
import receipt
from pathlib import Path

# 1. Write an output file (into the handoff workspace)
Path(receipt._receipts_dir / "hello.py").write_text("print('hello')\n")

# 2. Write a receipt
rec = receipt.write_receipt(
    task_id="task-001",
    from_agent="Maco",
    to_agent="Kim",
    prev_outputs=[],
    new_outputs=[{"path": "hello.py", "status": receipt.NOT_CHECKED}],
    typed_reason=receipt.PASS,
)

# 3. Downstream verifies before starting
ok, msg = receipt.verify_receipt("task-001", expect_from="Maco")
print(ok, msg)  # True, OK
```

## API

| Function / constant | Purpose |
|---|---|
| `write_receipt(task_id, from_agent, to_agent, prev_outputs, new_outputs, from_vendor=None, to_vendor=None, typed_reason=PASS, note="")` | Build a receipt dict and write it to `receipts/{task_id}.json`; empty output auto-downgrades to `REJECT` |
| `verify_receipt(task_id, expect_from, max_age=3600)` | Five-step verification (`density → scope → digest → epoch → verdict`), returns `(bool, reason)` |
| `density_check(receipt)` | Compute required-field coverage density, returns `(bool, metric)` |
| `content_digest(path)` | SHA-256 of a file's raw bytes, returns `sha256:<hex>` |
| `canonical_digest(obj)` | SHA-256 of JCS-canonical JSON, to absorb "semantically equal, byte-different" variance |
| `canonical_digest_file(path)` | Canonical digest of a file (JSON objects go through JCS; everything else falls back to content digest) |
| `digest_bytes(data)` | SHA-256 hex digest with `sha256:` prefix |
| `canonical_json(obj)` | RFC 8785 JCS canonical JSON (sorted keys, no extra whitespace) |

### typed_reason vocabulary

| Constant | Meaning |
|---|---|
| `PASS` | Handoff succeeded; downstream starts |
| `REJECT` | Handoff failed (including empty-output silent failure) |
| `UNKNOWN` | Insufficient evidence; moves to a reconcile track |
| `QUARANTINE` | Problematic but undetermined; isolated for review |
| `NOT_CHECKED` | Not yet checked |
| `INDETERMINATE` | Weak evidence, not converged |
| `CONFIRMED_UNAVAILABLE` | Confirmed truly absent (mechanism exists but produced nothing) |
| `CHECKED_EMPTY` | Checked, result is empty |

## Tests

```bash
python3 -m pytest test_receipt.py -v
```

Covers: normal handoff, tamper detection, expiry detection, empty-output auto-`REJECT`, source verification, and density check.

## Protocol spec

Full spec (schema, negative-example library, version roadmap) lives in [RECEIPT-BEARING-PROTOCOL.md](./RECEIPT-BEARING-PROTOCOL.md).

## Pipeline demo

`run_demo.py` is a concrete 5-agent collaboration pipeline:

```
Maco (OpenClaw) -> Kim (OpenClaw kimi) -> Claude (Claude Code) -> Codex (OpenAI) -> Sheila (Hermes)
  code              test                  code review            security review     README
```

Each agent writes a receipt on completion; the downstream agent verifies before starting. Run it with:

```bash
python3 run_demo.py
```

Results land in `output/`, and handoff credentials in `output/receipts/`.
