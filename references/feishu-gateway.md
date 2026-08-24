# 飛書 Agent 指揮部（多 agent 接入飛書 @ 派工）

將多個 AI agent 接入同一個飛書群，用戶可以 @ 佢哋對話、派工。呢個係「多 Agent 流水線」嘅另一種形態——由「串行 pipeline」變「群組並行派工」。

## 架構

```
飛書群「🏛️ Agent 指揮部」
   ├── 7 個 bot（Deep / Maco / Kim / Kiro / Cody / Sheila / Kimi）
   └── 網關 gateway.py（長連接，收 @ 訊息 → call 對應 agent CLI → 回覆群）
```

## 核心檔案

| 檔案 | 作用 |
|---|---|
| `~/.cc-connect/agents.config.json` | 7 個 bot 嘅 credential（appId + appSecret） |
| `~/.cc-connect/feishu-gateway/gateway.py` | 網關主程式 |
| `~/.cc-connect/feishu-gateway/run.sh` | launchd 啟動 script |
| `~/Library/LaunchAgents/com.drchai.feishu-gateway.plist` | launchd 服務 |

## 運作原理

1. 每個 bot 起一條飛書長連接（WebSocket）。
2. 群度有人 @ 某個 bot → 網關收到 mention 事件 → 判斷 @ 邊個 → call 嗰個 agent 嘅 headless CLI。
3. agent 回覆 → 網關以 bot 身份 send 返群。

## 已知坑（我哋踩過）

1. **版本 drift**：openclaw CLI 版本要同 config 一致（2026.6.11 vs 2026.7.1-2 會 call 唔起）。
2. **keepalive 斷線**：websockets 默認 20s protocol-level ping 會同飛書自己嘅 keepalive 衝突，要喺 gateway.py 加 `ping_interval=None` 禁用。
3. **無 greeting 好友請求**：飛書同 EigenFlux 兩邊都一樣——DM 要 friend 關係，先傾再決定加。

## 完整原始碼

`~/.cc-connect/feishu-gateway/gateway.py`
