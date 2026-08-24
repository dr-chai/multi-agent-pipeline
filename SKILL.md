---
name: multi-agent-pipeline
description: 搭建同運行一條由多個唔同 vendor 嘅 AI agent（OpenClaw、Claude Code、Codex、Hermes）組成嘅協作流水線，用 receipt-bearing 交接（epoch + digest + typed_reason）保證「先驗證先開工」。當用戶想搭建多 agent 協作、自動化 coding／QA／review／文檔流水線、或者落地 agent 交接協議（bounded-drain、epoch fence、receipt digest）時使用。
---

# 多 Agent 協作流水線（receipt-bearing 交接）

由唔同 vendor 嘅 AI agent 組成一條協作流水線（寫 code → 寫測試 → code review → security review → 寫文檔），交接用 **receipt**（epoch + digest + typed_reason）保證下游**先驗證先開工**，唔再係「丟 file 就算」。

## 核心概念（30 秒）

每個 agent 完成時寫一張 receipt，下游開工前驗三樣嘢：

1. **digest 對唔對** —— 對 output 重算 sha256，防篡改
2. **epoch 過唔過期** —— 防止讀到舊 state
3. **typed_reason 係咪 PASS** —— 唔係 PASS 就 fail-closed 唔開工

```json
{
  "task_id": "fib-002",
  "from": "Kim", "to": "Claude",
  "epoch": 1787448000,
  "typed_reason": "PASS",
  "outputs": {"fibonacci.py": "sha256:…", "test_fibonacci.py": "sha256:…"}
}
```

## 快速開始

```bash
# 1. 睇設定（裝晒 5 個 agent CLI + 授權）
# 2. 跑流水線
cd demo_agents && python3 run_demo.py
```

流水線會串行跑：`Maco 寫 code → Kim 寫測試 → Claude review → Codex review → Sheila 寫文檔`，每一步都有 receipt 交接。

## 參考文件

| 文件 | 內容 |
|---|---|
| `references/setup.md` | 安裝／設定（5 個 agent CLI + 授權）|
| `references/receipt-bearing.md` | receipt 交接設計 + 實測 |
| `references/feishu-gateway.md` | 飛書 Agent 指揮部（多 agent 接入飛書 @ 派工）|

## 行為指引

- 跑之前確認 5 個 agent CLI 都裝好 + 授權（見 setup.md）。
- receipt 係「可驗證」嘅核心，唔好刪走 receipts 目錄。
- 如果某個 agent 失敗，下游會 fail-closed 唔開工——呢個係預期行為，唔係 bug。
- 交接協議（bounded-drain、epoch fence、receipt digest）嘅更多背景，睇 `EigenFlux/知識庫/協議/多agent可靠性協議.md`。
