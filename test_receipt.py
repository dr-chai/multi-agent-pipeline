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
    assert "EPOCH-STALE" in msg


def test_future_epoch():
    task_id = "task_future_epoch"
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

    # Manually set epoch to a future time（結構性：issuer clock skew／亂填）
    receipt_path = receipt._receipts_dir / f"{task_id}.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    data["epoch"] = int(time.time()) + 99999
    receipt_path.write_text(receipt.canonical_json(data), encoding="utf-8")

    ok, msg = receipt.verify_receipt(task_id, expect_from="agent_a")
    assert ok is False
    assert "EPOCH-STRUCTURAL" in msg


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


# ── 見證層驗證（§12）正負例 ─────────────────────────────────────────
# 可證偽原則：每條母題一個「違反」負例 + 一個「守規矩」正例，證明佢會真攔。


def test_self_countersign():
    """負例 SELF-COUNTERSIGN：issuer == beneficiary（自簽）。"""
    ok, msg = receipt.check_independent("agent_a", "agent_a")
    assert ok is False
    assert "SELF-SIGNED" in msg


def test_independent_ok():
    ok, msg = receipt.check_independent("agent_a", "agent_b")
    assert ok is True


def test_missing_identity():
    ok, msg = receipt.check_independent(None, "agent_b")
    assert ok is False
    assert "MISSING-IDENTITY" in msg


def test_static_witness():
    """負例 STATIC-WITNESS：見證冇到期日（expires_at = None）。"""
    ok, msg = receipt.check_expiry(None, 100, "countersign_expires_at")
    assert ok is False
    assert "NO-EXPIRY" in msg


def test_expired_witness():
    """負例：到期日已過。"""
    ok, msg = receipt.check_expiry(50, 100, "countersign_expires_at")
    assert ok is False
    assert "EXPIRED" in msg


def test_expiry_ok():
    ok, msg = receipt.check_expiry(200, 100, "countersign_expires_at")
    assert ok is True


def test_fake_zero():
    """負例 FAKE-ZERO：計數欄位缺失（冇數過 ≠ 冇發生）。"""
    ok, msg = receipt.check_zero_emitted(None, "check_ran_n")
    assert ok is False
    assert "FAKE-ZERO" in msg


def test_zero_emitted_ok():
    """正例：0 都要落盤（寫咗 0 = 有數過）。"""
    ok, msg = receipt.check_zero_emitted(0, "check_ran_n")
    assert ok is True


def test_enum_drift():
    """負例 ENUM-DRIFT：value 超出閉集（就地加值 = 靜默）。"""
    ok, msg = receipt.check_closed_enum("BOGUS", {"PASS", "REJECT", "UNKNOWN"}, "typed_reason")
    assert ok is False
    assert "ENUM-DRIFT" in msg


def test_enum_ok():
    ok, msg = receipt.check_closed_enum("PASS", {"PASS", "REJECT", "UNKNOWN"}, "typed_reason")
    assert ok is True


# ── 見證層 block 綜合驗證（verify_witness_block）正負例 ──────────────


def test_witness_countersign_self_signed():
    """負例：countersign issuer == beneficiary（自簽）。"""
    w = {"countersign": {"issuer": "agent_a", "expires_at": 200}}
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is False
    assert "SELF-SIGNED" in msg


def test_witness_countersign_no_expiry():
    """負例：countersign 冇 expires_at（靜默失效）。"""
    w = {"countersign": {"issuer": "agent_b"}}
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is False
    assert "NO-EXPIRY" in msg


def test_witness_retention_self_retained():
    """負例：retention retained_by == beneficiary（自留底）。"""
    w = {"retention": {"retained_by": "agent_a", "retained_until": 200}}
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is False
    assert "SELF-SIGNED" in msg


def test_witness_counter_fake_zero():
    """負例：counters check_ran_n 缺失（冇數過 = 假 0）。"""
    w = {"counters": {"check_ran_n": None}}
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is False
    assert "FAKE-ZERO" in msg


def test_witness_enum_drift():
    """負例：typed_reason 超出閉集。"""
    w = {"typed_reason": "BOGUS"}
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is False
    assert "ENUM-DRIFT" in msg


def test_witness_block_ok():
    """正例：全部合法（獨立 + 到期日 + 零值 + 閉集）。"""
    w = {
        "countersign": {"issuer": "agent_b", "expires_at": 200},
        "retention": {"retained_by": "agent_b", "retained_until": 200},
        "counters": {"check_ran_n": 3, "observer_count_n": 2},
        "typed_reason": "PASS",
    }
    ok, msg = receipt.verify_witness_block(w, now=100, beneficiary="agent_a")
    assert ok is True