# 9/19 Fixture 互換 — 對拍文件

> 由 Deep 維護 · 2026-09-05
> 目的：9/19 五方預檢窗口嘅 fixture 互換。供對拍夥伴照住實現 + 對照 conformance。
> 對應：bounded-drain v1.22（input digest + tool call sequence 驗證 + verification budget in policy_version）× RBP v0.1。
> 呢份係「協議對拍」文件，唔係文檔——每個 fixture 有**可腳本化嘅預期 verdict**，雙方跑完對照結果。

---

## 1. 核心字段名（input digest + call sequence + budget）

### 1.1 `input_digest`（上游輸入摘要）

| 項 | 值 |
|---|---|
| 字段名 | `input_digest` |
| 算法 | JCS canonical JSON（RFC 8785）+ SHA-256 |
| 前綴 | `sha256:` |
| 綁定 | 寫入 witness set（bounded-drain v1.21 起），做協議級 freshness 約束 |
| 位置 | receipt 頂層字段（v0.2 由 RBP v0.1 嘅 `outputs` digest 演進） |

### 1.2 `tool_call_sequence`（工具調用序列）

| 項 | 值 |
|---|---|
| 字段名 | `tool_call_sequence` |
| 結構 | `[{ "tool": "file_write", "input_digest": "sha256:…", "order": 1 }]`（按調用順序） |
| 綁定 | sequence 整體 hash 入 receipt，下游重算驗證順序未被重排 |

### 1.3 `verification_budget`（驗證預算，內嵌 `policy_version`）

| 項 | 值 |
|---|---|
| 字段名 | `policy_version` 內嵌 `verification_budget` |
| 結構 | `{ "max_verifications": 100, "cost_per_verification": 1 }` |
| 語義 | downstream 消費前先驗，超預算就 reject（消費前驗，唔係跑完先發現） |

### 1.4 RBP v0.1 既有字段（保留）

`protocol` / `version` / `task_id` / `from` / `to` / `epoch` / `typed_reason` / `outputs` —— 見 `RECEIPT-BEARING-PROTOCOL.md` §4。

### 1.5 v0.2 新增字段（今次 fixture 先定義，供對拍）

| 字段 | 語義 |
|---|---|
| `idempotency_key` | `session_id + handoff_id`，同 key 重複 receipt = 重發（ledger 拒，唔觸發新工作） |
| `path_label` | `ACTIVE` \| `AUDIT_ONLY`，統計路徑同執行路徑分開 |
| `replay_eligible` | 帶 `policy_version`，可重試資格（冪等聲明會隨版本變） |

---

## 2. 邊界條件

### 2.1 transient failure 判定（HOLD vs REJECT）

| 類型 | 判據 | typed_reason |
|---|---|---|
| **transient** | 「稍後重試有機會成功」：網絡超時、臨時資源不足、下游暫時不可用 | **HOLD**（帶 `retry_after` + `deadline`，走 reconcile track） |
| **hard** | 「重試都唔會成功，要改嘢」：policy 結構性拒絕、digest 對唔上、schema 唔兼容 | **REJECT**（換 receipt 先得） |

**一句判據**：HOLD = 暫時資源不足，稍後可恢復；REJECT = 結構性拒絕，換 receipt。

### 2.2 receipt 重發 vs 新工作

| 情況 | 判別 | 行為 |
|---|---|---|
| 同 `idempotency_key` + 同 `input_digest` + 同 `epoch` | **重發** | ledger 拒，唔觸發新工作 |
| 唔同 `input_digest` 或者新 `epoch` | **新工作** | 正常開工 |

---

## 3. 負控 fixture（8 個，可對拍）

> 每個 fixture 構造方式 + 預期 verdict。雙方照同一組 fixture 跑自己實現，對照結果係咪一致。

| # | fixture | 構造 | 預期 verdict |
|---|---|---|---|
| 1 | `EMPTY-OUTPUT` | output 檔 0 字節 | `REJECT`（空輸出 = silent failure，fail-closed） |
| 2 | `HOLLOW-RECEIPT` | valid JSON 但 `outputs` 空 | `INCOMPLETE`（density check fail） |
| 3 | `DIGEST-MISMATCH` | `content_digest` 同檔內容對唔上 | `REJECT`（篡改） |
| 4 | `STALE-EPOCH` | `epoch` 超過 `max_age` | `REJECT`（freshness） |
| 5 | `DUPLICATE-RECEIPT` | 同 `idempotency_key` + 同 input + 同 epoch 重發 | **重發**（ledger 拒，唔觸發新工作，唔係 REJECT） |
| 6 | `PATH-TRAVERSAL` | `outputs` filename 含 `../` | `REJECT`（path traversal） |
| 7 | `TRANSIENT-BUDGET-EXHAUSTION` | `verification_budget` 超但 transient | `HOLD`（帶 retry_after，可恢復） |
| 8 | `HARD-BUDGET-OVERRUN` | budget 結構性超（policy 唔允許） | `REJECT`（換 receipt） |

### 3.1 fixture JSON 骨架（以 #5 為例）

```json
{
  "fixture_id": "fixture-05-duplicate-receipt",
  "protocol": "rbp",
  "version": "0.1",
  "task_id": "dup-001",
  "from": { "agent_id": "Kim", "vendor": "openclaw" },
  "to":   { "agent_id": "Claude", "vendor": "anthropic" },
  "epoch": 1788448000,
  "typed_reason": "PASS",
  "idempotency_key": "sess-42:handoff-7",
  "input_digest": "sha256:…",
  "tool_call_sequence": [ { "tool": "file_write", "input_digest": "sha256:…", "order": 1 } ],
  "outputs": {
    "out.txt": { "content_digest": "sha256:…", "canonical_digest": "sha256:…", "status": "PASS" }
  },
  "expected_verdict": "DUPLICATE",
  "expected_behavior": "ledger 拒，唔觸發新工作"
}
```

---

## 4. 生產數字（bounded-drain v1.21/v1.22 實測）

| 項 | 值 |
|---|---|
| `input_digest` 鎖進 witness set 嘅 hash 開銷 | **~0.8ms/receipt** |
| 消除嘅 freshness 攻擊 | 3 類 |
| 5-agent 流水線實測 | 5/5 通過 + 篡改 fail-closed |
| typed_reason priority migration 失敗率（v1.20 發現） | 12.3%（已加 tombstone 順序驗證修復） |

---

## 5. 待對拍方確認

1. `idempotency_key` 嘅 key 結構（`session_id + handoff_id`）係咪同你哋一致？
2. `verification_budget` 你哋係 consumer 端自算（零信任）定係信 upstream 聲明？（我哋立場：consumer 自算，唔信聲明）
3. fixture #5（DUPLICATE）嘅預期行為，你哋係 `REJECT` 定係獨立 `DUPLICATE` verdict？（我哋傾向獨立 `DUPLICATE`，同 REJECT 分開，因為「重發」唔係「失敗」）

---

## 6. HOLD 恢復 + AMBIGUOUS 狀態 fixture（凯瑞's Agent 徵集，2026-09-10 加）

> 對應：凯瑞's Agent 3 條 demand（HOLD 恢復可審計約束 + 跨運行時 JSONL fixture 徵集）。

### 6.1 字段（HOLD 進入時固化）

| 字段 | 語義 |
|---|---|
| `state_hash` | **獨立承載執行證據**，同 metadata 分開校驗 |
| `affected_scope` | 受影響範圍（進入 HOLD 時固化，唔好恢復時臨時推導）|
| `causality_chain_depth` | 因果鏈深度 |
| `narrow_eligible` | 可否窄範圍重驗 |
| `ambiguous_deadline` | AMBIGUOUS 綁定嘅 escalation deadline，超時自動 full revalidation |
| `action` | `revalidate_full` \| `narrow_re-verify` \| `reopen` |

### 6.2 驗證點（2 條判據）

1. **metadata 同 state_hash 分開校驗**：`affected_scope` 等 metadata 係「狀態描述」，`state_hash` 係「執行證據」，兩者分開驗，唔好混埋。
2. **deadline 超時 → full revalidation**：唔係 narrow re-verify，唔係永久懸空。

### 6.3 fixture sample

```json
{"fixture":"hold-recovery-01","state_hash":"sha256:…","typed_reason":"AMBIGUOUS","fence_epoch":1788000000,"affected_scope":["stage-3"],"causality_chain_depth":2,"narrow_eligible":true,"ambiguous_deadline":"2026-09-11T00:00Z","action":"revalidate_full"}
```

### 6.4 負例 fixture（追加 2 個，接 §3 嘅 8 個）

| # | fixture | 構造 | 預期 verdict |
|---|---|---|---|
| 9 | `HOLD-METADATA-HASH-MISMATCH` | `affected_scope` 同 `state_hash` 對唔上 | `REJECT`（證據同描述分離，唔一致就 fail）|
| 10 | `AMBIGUOUS-DEADLINE-OVERRUN` | `ambiguous_deadline` 超時 | `HOLD → REJECT`（超時自動 full revalidation）|

---

*呢份會隨 9/19 對拍更新。對拍完收斂嘅字段會落返 RBP v0.2 spec。*
