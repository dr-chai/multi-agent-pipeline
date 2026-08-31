import json
import time
from pathlib import Path

import receipt
import pytest


@pytest.fixture(autouse=True)
def clean_receipts_dir():
    """Clear receipts directory before and after each test."""
    rd = receipt._receipts_dir
    if rd.exists():
        for f in rd.iterdir():
            f.unlink()
    else:
        rd.mkdir(parents=True, exist_ok=True)
    yield
    if rd.exists():
        for f in rd.iterdir():
            f.unlink()


def test_normal_handoff():
    task_id = "task_normal"
    py_path = receipt._receipts_dir / "hello.py"
    md_path = receipt._receipts_dir / "notes.md"
    py_path.write_text("print('hello')", encoding="utf-8")
    md_path.write_text("# Hello\n", encoding="utf-8")

    prev_outputs = [{"path": "hello.py", "status": receipt.NOT_CHECKED}]
    new_outputs = [{"path": "notes.md", "status": receipt.NOT_CHECKED}]

    rec = receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
        note="normal handoff",
    )

    assert rec["typed_reason"] == receipt.PASS

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is True
    assert msg == "OK"


def test_tampering():
    task_id = "task_tamper"
    out_path = receipt._receipts_dir / "data.txt"
    out_path.write_text("original content", encoding="utf-8")

    prev_outputs = []
    new_outputs = [{"path": "data.txt", "status": receipt.NOT_CHECKED}]

    receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
    )

    # Tamper with the output file after receipt is written
    out_path.write_text("tampered content", encoding="utf-8")

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is False
    assert "mismatch" in msg


def test_expired():
    task_id = "task_expired"
    out_path = receipt._receipts_dir / "report.md"
    out_path.write_text("# Report\n", encoding="utf-8")

    prev_outputs = []
    new_outputs = [{"path": "report.md", "status": receipt.NOT_CHECKED}]

    receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
    )

    # Manually set epoch to an old time
    receipt_path = receipt._receipts_dir / f"{task_id}.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    data["epoch"] = int(time.time()) - 99999
    receipt_path.write_text(receipt.canonical_json(data), encoding="utf-8")

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is False
    assert "stale" in msg


def test_empty_output():
    task_id = "task_empty"
    out_path = receipt._receipts_dir / "empty.txt"
    out_path.write_bytes(b"")

    prev_outputs = []
    new_outputs = [{"path": "empty.txt", "status": receipt.NOT_CHECKED}]

    rec = receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
    )

    assert rec["typed_reason"] == receipt.REJECT

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is False
    assert "not PASS" in msg


def test_wrong_source():
    task_id = "task_scope"
    out_path = receipt._receipts_dir / "code.py"
    out_path.write_text("x = 1", encoding="utf-8")

    prev_outputs = []
    new_outputs = [{"path": "code.py", "status": receipt.NOT_CHECKED}]

    receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
    )

    # Pass wrong expect_from, everything else intact
    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_z")
    assert ok is False
    assert "scope mismatch" in msg


def test_density_check():
    task_id = "task_density"
    out_path = receipt._receipts_dir / "file.txt"
    out_path.write_text("content", encoding="utf-8")

    prev_outputs = []
    new_outputs = [{"path": "file.txt", "status": receipt.NOT_CHECKED}]

    receipt.write_receipt(
        task_id=task_id,
        from_agent="agent_a",
        to_agent="agent_b",
        prev_outputs=prev_outputs,
        new_outputs=new_outputs,
        typed_reason=receipt.PASS,
    )

    # Remove enough required fields to drop density below 0.6
    receipt_path = receipt._receipts_dir / f"{task_id}.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    for field in ("epoch", "from", "to", "outputs"):
        data.pop(field, None)
    receipt_path.write_text(receipt.canonical_json(data), encoding="utf-8")

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is False
    assert "INCOMPLETE" in msg

    # Direct density_check with low-density data
    d_ok, metric = receipt.density_check(data)
    assert d_ok is False
    assert metric < 0.6