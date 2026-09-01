# Receipt-Bearing Protocol (RBP) — 多 Agent 協作交接驗證協議

![CI](https://github.com/dr-chai/multi-agent-pipeline/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Protocol](https://img.shields.io/badge/RBP-v0.1-blue.svg)

> 唔做信箱，做「交接驗證」——先驗證先開工、fail-closed。
>
> 協議規格見 [RECEIPT-BEARING-PROTOCOL.md](./RECEIPT-BEARING-PROTOCOL.md)

## 核心概念

RBP 係一條**跨 vendor agent 交接驗證協議**。每個 agent 完成任務後寫一張 **receipt**（交接憑證），下游開工前**先驗證、先開工**；任何一樣驗唔過就 fail-closed（唔開工）。

### Receipt 三層保證

| 層 | 字段 | 作用 |
|---|---|---|
| 時效層 | `epoch` | 防止讀過期 state，`now - epoch ≤ max_age` |
| 完整性層 | `content_digest` / `canonical_digest` | 防止篡改，下游重算 hash 比對 |
| 決策層 | `typed_reason` | 類型化記錄「點解呢步係咁」，唔係 PASS 就 fail-closed |

### Fail-closed

任何驗證失敗 = 唔開工。空結果（0 字節）自動降級 REJECT，唔可以同成功混為一談。

## 安裝

純標準庫，零第三方依賴：

```bash
# 需要 Python 3.8+
python3 -c "import receipt; print('OK')"
```

依賴：`hashlib`、`json`、`time`、`pathlib`（全部標準庫）。

## 快速開始

```python
import receipt
from pathlib import Path

# 1. 寫 output 檔
Path(receipt._receipts_dir / "hello.py").write_text("print('hello')\n")

# 2. 寫 receipt
rec = receipt.write_receipt(
    task_id="task-001",
    from_agent="Maco",
    to_agent="Kim",
    prev_outputs=[],
    new_outputs=[{"path": "hello.py", "status": receipt.NOT_CHECKED}],
    typed_reason=receipt.PASS,
)

# 3. 下游驗證
ok, msg = receipt.verify_receipt("task-001", expect_from="Maco")
print(ok, msg)  # True, OK
```

## API

| 函數 / 常數 | 用途 |
|---|---|
| `write_receipt(task_id, from_agent, to_agent, prev_outputs, new_outputs, ...)` | 建 receipt dict，寫入 `receipts/{task_id}.json`；空輸出自動降級 REJECT |
| `verify_receipt(task_id, expect_from, max_age=3600)` | 五步驗證（density → scope → digest → epoch → verdict），返 `(bool, 原因)` |
| `density_check(receipt)` | 計算 required fields 覆蓋密度，返 `(bool, metric)` |
| `content_digest(path)` | 對檔案原始 bytes 做 SHA-256，返 `sha256:<hex>` |
| `canonical_digest(obj)` | 對 JCS canonical JSON 做 SHA-256，消解「語義相同、字節不同」 |
| `canonical_digest_file(path)` | 對檔案做 canonical digest（JSON 走 JCS，其他 fall back content_digest） |
| `digest_bytes(data)` | SHA-256 hex digest，前綴 `sha256:` |
| `canonical_json(obj)` | RFC 8785 JCS canonical JSON（鍵按 UTF-8 排序、無多餘空白） |

### typed_reason 詞表

| 常數 | 語義 |
|---|---|
| `PASS` | 交接成功，下游開工 |
| `REJECT` | 交接失敗（含空輸出 silent failure） |
| `UNKNOWN` | 證據不足，進 reconcile track |
| `QUARANTINE` | 有問題但未定性，隔離待 review |
| `NOT_CHECKED` | 未檢查 |
| `INDETERMINATE` | 有弱證據但未收斂 |
| `CONFIRMED_UNAVAILABLE` | 確認「真係冇」 |
| `CHECKED_EMPTY` | 檢查過，結果係空 |

## 測試

```bash
cd 產品/multi-agent-pipeline
python3 -m pytest test_receipt.py -v
```

測試涵蓋：正常交接、篡改檢測、過期檢測、空輸出自動 REJECT、來源驗證、density check。

## 協議規格

詳細規格（schema、負例庫、版本 roadmap）見 [RECEIPT-BEARING-PROTOCOL.md](./RECEIPT-BEARING-PROTOCOL.md)。

## 流水線 Demo

`run_demo.py` 係一條 5-agent 協作流水線實例：

```
Maco (OpenClaw) → Kim (OpenClaw kimi) → Claude (Claude Code) → Codex (OpenAI) → Sheila (Hermes)
 code              test               code review          security review    README
```

每個 agent 完成後寫 receipt，下游開工前 verify。執行：

```bash
python3 run_demo.py
```

完成後 `output/` 有晒成果，`output/receipts/` 有晒交接憑證。
