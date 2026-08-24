# Dr. Chai's Multi-Agent Pipeline

A **cross-vendor multi-agent pipeline** with **receipt-bearing handoff** — chain 5 AI agents from different vendors, and every handoff carries a verifiable receipt (epoch + digest + typed_reason) so the downstream agent **verifies before it starts**.

## What it is

```
Maco writes code → Kim writes tests → Claude reviews → Codex reviews → Sheila writes docs
        └──── every step writes a receipt, downstream verifies first ────┘
```

## Why it's different

| | Typical multi-agent | Ours |
|---|---|---|
| Handoff | just drop a file | write a receipt, verify before start |
| Tampering | silently reads stale file | digest mismatch → fail-closed |
| Failure tracing | restart from scratch | receipt shows exactly where it broke |
| Empty output | treated as success | auto-flagged `REJECT` (silent-failure fail-closed) |

## The receipt

```json
{
  "task_id": "fib-002",
  "from": "Kim",
  "to": "Claude",
  "epoch": 1787448000,
  "typed_reason": "PASS",
  "outputs": {
    "fibonacci.py": "sha256:3f9a…",
    "test_fibonacci.py": "sha256:8b2c…"
  }
}
```

Downstream verifies three things before starting:
1. **digest** matches (recompute sha256 on each output) — tamper-proof
2. **epoch** not expired — no stale state
3. **typed_reason** is PASS — otherwise fail-closed

## Quick start

```bash
# 1. Install the 5 agent CLIs (see references/setup.md)
# 2. Run the pipeline
python3 run_demo.py
```

One command produces: code + tests + two reviews + README, with a full receipt trail in `receipts/`.

## Verified in production (not vaporware)

- ✅ Full 5-agent run passes — all 5 receipts `PASS`, `fib()` returns correct sequence
- ✅ Tamper test → `digest mismatch` → fail-closed
- ✅ Empty-output test → auto `REJECT` → downstream fail-closed

## Directory

| File | What |
|---|---|
| `run_demo.py` | pipeline with receipt-bearing handoff |
| `SKILL.md` | installable agent skill |
| `RECEIPT-BEARING.md` | design + real-world test + the bug we hit and fixed |
| `references/setup.md` | install/auth guide |
| `references/feishu-gateway.md` | multi-agent Feishu command-center (alternative mode) |

## Background

The receipt-bearing handoff comes from the multi-agent reliability protocol work (bounded-drain, epoch fence, receipt digest) we've been converging on across the EigenFlux agent network — not paper theory, this pipeline runs it.

## License

MIT
