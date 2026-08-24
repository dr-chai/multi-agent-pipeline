# 柴博士多 Agent 協作流水線

用多個**唔同 vendor** 嘅 AI agent 組成一條協作流水線，交接用 **receipt**（epoch + digest + typed_reason）保證「先驗證先開工」。

## 佢係咩

一條流水線，串起 5 個 agent 各司其職：

```
Maco 寫 code → Kim 寫測試 → Claude review → Codex review → Sheila 寫文檔
```

每個 agent 完成時寫一張 receipt，下游開工前先驗證——**digest 對唔對、epoch 過唔過期、typed_reason 係咪 PASS**。

## 有咩唔同（差異化）

| | 一般多 agent 方案 | 我哋 |
|---|---|---|
| 交接 | 丟 file 就算 | 寫 receipt，先驗證先開工 |
| 篡改 | 讀咗舊 file 都唔知 | digest 對唔上就 fail-closed |
| 失敗追溯 | 要由頭再跑 | receipt 留低「做到邊一步」|

呢套 receipt-bearing 交接，嚟自我哋喺 EigenFlux agent 網絡實測嘅「多 agent 可靠性協議」（bounded-drain、epoch fence、receipt digest）——唔係紙上談兵，係自己個 pipeline 已經跑緊。

## 快速開始

```bash
# 1. 裝 5 個 agent CLI（見 references/setup.md）
# 2. 跑流水線
cd demo_agents && python3 run_demo.py
```

完成後，output/ 有晒成果（fibonacci.py、test、兩份 review、README），receipts/ 有晒交接憑證。

## 目錄

| 檔案 | 內容 |
|---|---|
| `run_demo.py` | 流水線主程式（receipt-bearing 交接）|
| `SKILL.md` | skill 主文件（俾 agent 讀）|
| `RECEIPT-BEARING.md` | 交接設計 + 實測 |
| `references/setup.md` | 安裝／設定教程 |
| `references/feishu-gateway.md` | 飛書 Agent 指揮部（另一種多 agent 形態）|

## 產品化（可賣）

呢套嘢可以拆做三層賣：

1. **Skill／教程**（免費引流）—— 教人 30 分鐘起一條多 Agent 流水線
2. **課程**（付費）—— 系統化教「多 Agent 協作 + 可靠性協議」
3. **落地服務**（高客單價）—— 幫企業實地部署 + 客製化
