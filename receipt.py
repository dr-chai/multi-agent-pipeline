"""
Receipt-Bearing Protocol (RBP) — 跨 vendor agent 交接驗證協議 v0.1
純標準庫實現，無第三方依賴。

約定：
- 交接工作區 = 本檔同層嘅 receipts/ 目錄（outputs 同 receipt 都放呢度；v0.2 會抽做可配置 base_dir）
- receipt 嘅 outputs 字段 = map：filename -> {content_digest, canonical_digest, status}

v0.1 已知取捨（待 v0.2）：
- 驗簽（DID/VC）略過，只驗 digest
- per-output status 用 PASS/REJECT（§6.2 空輸出四態係 v0.2 增強）
- from/to.vendor 預設 fallback 做 agent_id（caller 應傳真實 vendor）
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

# ── typed_reason 詞表 ──────────────────────────────────────────────
PASS = "PASS"
REJECT = "REJECT"
UNKNOWN = "UNKNOWN"
QUARANTINE = "QUARANTINE"

NOT_CHECKED = "NOT_CHECKED"
INDETERMINATE = "INDETERMINATE"
CONFIRMED_UNAVAILABLE = "CONFIRMED_UNAVAILABLE"
CHECKED_EMPTY = "CHECKED_EMPTY"

UNSET = "UNSET"
EMPTY = "EMPTY"

REQUIRED_FIELDS = [
    "protocol", "version", "task_id",
    "from", "to", "epoch",
    "typed_reason", "outputs",
]
MIN_DENSITY = 0.6

# ── 目錄 ────────────────────────────────────────────────────────────
_receipts_dir = Path(__file__).parent / "receipts"   # 交接工作區（outputs + receipt）
_receipts_dir.mkdir(exist_ok=True)


# ── canonical_json：RFC 8785 JCS ───────────────────────────────────
def canonical_json(obj) -> str:
    """JCS canonical JSON：鍵按 UTF-8 排序、無多餘空白。

    RFC 8785 §3.2.2.2：非控制字符必須原樣 UTF-8 輸出，唔可以轉 \\uXXXX 轉義。
    所以 ensure_ascii=False（Python json.dumps 預設 True 會轉義非 ASCII，係 JCS 違規）。
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


# ── digest 工具 ─────────────────────────────────────────────────────
def digest_bytes(data: bytes) -> str:
    """SHA-256 hex digest，前綴 'sha256:'。"""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def content_digest(path: Path) -> str:
    """對檔案原始 bytes 做 digest_bytes。"""
    return digest_bytes(path.read_bytes())


def canonical_digest(obj) -> str:
    """對 canonical_json(obj) 的 UTF-8 bytes 做 digest_bytes。"""
    return digest_bytes(canonical_json(obj).encode("utf-8"))


def canonical_digest_file(path: Path) -> str:
    """對檔案做 canonical digest：
    - JSON object → JCS + SHA-256（消解「語義相同、字節不同」）
    - 其他（含非 JSON、JSON list/int/str）→ fall back 做 content_digest（raw bytes）
    （負例 NON-JSON-CANONICALIZE：對非 JSON 做 json.loads 會 crash；JSON list 走錯路徑。）"""
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError):
        return digest_bytes(raw)  # fall back 做 content_digest
    return canonical_digest(obj)


# ── 路徑／ID 安全 ───────────────────────────────────────────────────
def _safe_name(name) -> bool:
    """只接受單一相對 filename（拒 absolute／`..`／path separator／NUL／首尾空白）。
    （負例：path traversal 逃逸 receipts/ 目錄。）"""
    if not isinstance(name, str) or not name:
        return False
    if name != name.strip() or "\x00" in name:
        return False
    if name in (".", "..") or ".." in name:
        return False
    if "/" in name or "\\" in name:
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    return True


def _safe_task_id(task_id) -> bool:
    """task_id 只允許 [A-Za-z0-9_-]{1,128}，防寫出 receipts/ 目錄。"""
    return isinstance(task_id, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id))


# ── write_receipt ──────────────────────────────────────────────────
def write_receipt(
    task_id: str,
    from_agent: str,
    to_agent: str,
    prev_outputs: list,
    new_outputs: list,
    from_vendor: str = None,
    to_vendor: str = None,
    typed_reason: str = PASS,
    note: str = "",
) -> dict:
    """
    構建 receipt dict 並寫入 receipts/{task_id}.json。
    - outputs 累積 prev_outputs + new_outputs，落成 map：filename -> {content_digest, canonical_digest, status}
    - 空 output（0 bytes）自動降級 REJECT（fail-closed）
    - 空 path（冇產出）略過，唔落 map
    prev_outputs / new_outputs 每項係 str filename 或 dict {path, status}。
    """
    if not _safe_task_id(task_id):
        raise ValueError(f"invalid task_id: {task_id!r}")

    outputs: dict = {}   # filename -> {content_digest, canonical_digest, status}
    final_reason = typed_reason

    for src in (prev_outputs, new_outputs):
        for item in src:
            if isinstance(item, dict):
                path_str = item.get("path", "")
            else:
                path_str = str(item)

            if not path_str:
                continue   # 空 path = 冇產出，略過

            if not _safe_name(path_str):
                final_reason = REJECT   # 唔安全 path（../ 等）fail-closed
                continue

            p = _receipts_dir / path_str
            if not p.exists():
                final_reason = REJECT
                outputs[path_str] = {
                    "content_digest": digest_bytes(b""),
                    "canonical_digest": digest_bytes(b""),
                    "status": REJECT,
                }
                continue

            raw_bytes = p.read_bytes()
            if len(raw_bytes) == 0:
                final_reason = REJECT   # 空輸出 = silent failure，fail-closed
                outputs[path_str] = {
                    "content_digest": digest_bytes(b""),
                    "canonical_digest": digest_bytes(b""),
                    "status": REJECT,
                }
                continue

            outputs[path_str] = {
                "content_digest": content_digest(p),
                "canonical_digest": canonical_digest_file(p),
                "status": PASS,
            }

    receipt = {
        "protocol": "rbp",
        "version": "0.1",
        "task_id": task_id,
        "from": {"agent_id": from_agent, "vendor": from_vendor or from_agent},
        "to": {"agent_id": to_agent, "vendor": to_vendor or to_agent},
        "epoch": int(time.time()),
        "typed_reason": final_reason,
        "note": note,
        "outputs": outputs,
    }

    out_path = _receipts_dir / f"{task_id}.json"
    # 原子替換：臨時檔 + fsync + rename，防「寫一半」俾讀到（receipt chain 假設原子 commit 負例）
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(canonical_json(receipt))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, out_path)
    return receipt


# ── verify_receipt ─────────────────────────────────────────────────
def verify_receipt(
    task_id: str,
    expect_from: str,
    max_age: int = 3600,
) -> tuple:
    """
    五步驗證，順序：density → scope → digest → epoch → verdict。
    任何一步唔過回傳 (False, 原因字串)，fail-closed。
    ① 驗簽（v0.1 略過）→ 由 scope 做身份前置校驗，再驗 digest（防 scope 被 digest 掩蓋）。
    """
    path = _receipts_dir / f"{task_id}.json"

    if not path.exists():
        return False, f"receipt file not found: {path}"

    try:
        receipt = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"failed to read receipt: {exc}"

    if not isinstance(receipt, dict):
        return False, "receipt is not a JSON object"

    # ── ① density（deserialization 之後、semantic verification 之前）──
    ok, density = density_check(receipt)
    if not ok:
        return False, f"INCOMPLETE: density {density:.2f} < {MIN_DENSITY}"

    # ── ② scope：身份前置校驗（v0.1 略過驗簽，scope 緊接 density 之後）──
    sender = receipt.get("from", {})
    if not isinstance(sender, dict) or sender.get("agent_id") != expect_from:
        return False, f"scope mismatch: receipt.from={sender}, expected={expect_from}"

    # ── ③ digest：對 outputs 每個檔重算 ─────────────────────────────
    outputs = receipt.get("outputs", {})
    if not isinstance(outputs, dict):
        return False, "outputs is not a map"
    for name, meta in outputs.items():
        if not _safe_name(name):
            return False, f"unsafe output name: {name!r}"
        if not isinstance(meta, dict):
            return False, f"output metadata not a map for {name!r}"
        p = _receipts_dir / name
        if not p.is_file():
            return False, f"output file missing: {name}"
        try:
            if content_digest(p) != meta.get("content_digest"):
                return False, f"content_digest mismatch for {name}"
            if canonical_digest_file(p) != meta.get("canonical_digest", ""):
                return False, f"canonical_digest mismatch for {name}"
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            return False, f"digest failed for {name}: {exc}"

    # ── ④ epoch：本地時鐘，防舊 state 同未來時間 ────────────────────
    # STALE-EPOCH 拆兩子例（結構性 vs 時效性，同 Pikature 收斂 2026-09）：
    #   結構性（EPOCH-STRUCTURAL）= epoch 本身無效（type 錯／未來時間），issuer 錯，換 receipt 先得，重試無用。
    #   時效性（EPOCH-STALE）= epoch 有效但過期（age > max_age），freshness 問題，可要求重新簽發。
    epoch = receipt.get("epoch", 0)
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return False, f"EPOCH-STRUCTURAL: invalid epoch type {type(epoch).__name__}"
    age = int(time.time()) - epoch
    if age < 0:
        return False, f"EPOCH-STRUCTURAL: future epoch age={age}s (issuer clock skew / forged timestamp)"
    if age > max_age:
        return False, f"EPOCH-STALE: age={age}s > max_age={max_age}s (freshness)"

    # ── ⑤ verdict ────────────────────────────────────────────────────
    if receipt.get("typed_reason") != PASS:
        return False, f"verdict not PASS: {receipt.get('typed_reason')}"

    return True, "OK"


# ── density_check ──────────────────────────────────────────────────
def density_check(receipt: dict) -> tuple:
    """
    計算 receipt 中 required fields 的覆蓋密度 + outputs 非空。
    回傳 (通過?, metric)。
    （負例 HOLLOW-RECEIPT：valid JSON 但內容空洞，outputs 空 → 不過。）"""
    present = sum(
        1 for field in REQUIRED_FIELDS
        if field in receipt and receipt[field] is not None
    )
    metric = present / len(REQUIRED_FIELDS)
    if metric < MIN_DENSITY:
        return False, metric
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict) or len(outputs) == 0:
        return False, 0.0   # 空 outputs = hollow receipt，fail
    return True, metric


# ── 見證層驗證（§12 見證與時效 · v0.3 前置）────────────────────────
# 「誰」母題四條，逐條可證偽（能被負控測出來的才叫約束）：
#   1. 獨立於得益方（自簽 ≠ 獨立見證）
#   2. 有到期日（冇到期日嘅身分一定靜默失效）
#   3. 零值必發（寫 0 = 將未發生偽裝成已窮盡 = 假 0）
#   4. 閉集（超出即 UNKNOWN，就地加值 = 靜默）


def check_independent(issuer_id, beneficiary_id) -> tuple:
    """驗證 issuer 獨立於 beneficiary（自簽 ≠ 獨立見證）。
    負例 SELF-COUNTERSIGN：見證由受益方自簽。"""
    if issuer_id is None or beneficiary_id is None:
        return False, "MISSING-IDENTITY: issuer/beneficiary 缺一，無法判定獨立性"
    if issuer_id == beneficiary_id:
        return False, f"SELF-SIGNED: issuer={issuer_id} == beneficiary（自簽 ≠ 獨立見證）"
    return True, "OK"


def check_expiry(expires_at, now, field_name="expiry") -> tuple:
    """驗證「有到期日」且未過期（冇到期日嘅身分一定靜默失效）。
    負例 STATIC-WITNESS：見證冇到期日（三年前見證 = 今日見證）。"""
    if expires_at is None:
        return False, f"NO-EXPIRY: {field_name} 缺到期日（冇到期日 = 靜默失效）"
    if expires_at <= now:
        return False, f"EXPIRED: {field_name} expires_at={expires_at} <= now={now}"
    return True, "OK"


def check_zero_emitted(value, field_name) -> tuple:
    """驗證「零值必發」——計數欄位唔可以缺失（None）。
    負例 FAKE-ZERO：寫 0 = 將未發生偽裝成已窮盡；缺失 = 冇數過 = 假 0。"""
    if value is None:
        return False, f"FAKE-ZERO: {field_name} 缺計數（冇數過 ≠ 冇發生）"
    return True, "OK"


def check_closed_enum(value, allowed_set, field_name) -> tuple:
    """驗證「閉集」——value 必須喺 allowed_set 內。
    負例 ENUM-DRIFT：超出閉集 = 靜默（就地加值），要判 UNKNOWN。"""
    if value not in allowed_set:
        return False, f"ENUM-DRIFT: {field_name}={value!r} 超出閉集 {allowed_set}（超出即 UNKNOWN）"
    return True, "OK"


def verify_witness_block(w: dict, now: int, beneficiary: str) -> tuple:
    """驗證見證層 block 守「誰」母題四條（v0.3 擴展字段）。
    w 結構：{
      "countersign": {"issuer": str, "expires_at": int},      # 見證：獨立 + 到期日
      "retention":   {"retained_by": str, "retained_until": int},  # 留存：獨立 + 到期日
      "counters":    {"check_ran_n": int, "observer_count_n": int},  # 計數：零值必發
      "typed_reason": str,                                    # 閉集（超出即 UNKNOWN）
    }
    逐條用四母題函數驗證，任何一條違反即 fail（fail-closed）。"""
    # 見證：issuer 獨立於 beneficiary + 有到期日
    cs = w.get("countersign")
    if cs is not None:
        ok, msg = check_independent(cs.get("issuer"), beneficiary)
        if not ok:
            return False, f"countersign: {msg}"
        ok, msg = check_expiry(cs.get("expires_at"), now, "countersign.expires_at")
        if not ok:
            return False, f"countersign: {msg}"

    # 留存：retained_by 獨立於 beneficiary + 有到期日（自留底 = 冇人核）
    rt = w.get("retention")
    if rt is not None:
        ok, msg = check_independent(rt.get("retained_by"), beneficiary)
        if not ok:
            return False, f"retention: {msg}"
        ok, msg = check_expiry(rt.get("retained_until"), now, "retention.retained_until")
        if not ok:
            return False, f"retention: {msg}"

    # 計數：零值必發（缺失 = 冇數過 = 假 0）
    counters = w.get("counters", {})
    for f in ("rejected_write_n", "check_ran_n", "expiry_breach_observed_n", "observer_count_n"):
        if f in counters:
            ok, msg = check_zero_emitted(counters.get(f), f)
            if not ok:
                return False, msg

    # 閉集：typed_reason 超出即 UNKNOWN
    tr = w.get("typed_reason")
    if tr is not None:
        ok, msg = check_closed_enum(tr, {PASS, REJECT, UNKNOWN, QUARANTINE}, "typed_reason")
        if not ok:
            return False, msg

    return True, "OK"
