# 安裝／設定（5 個 agent CLI）

呢套流水線用 5 個唔同 vendor 嘅 AI agent，全部喺本地行（headless CLI）。逐個裝 + 授權。

## Agent 一覽

| Agent | 本體 | CLI 路徑 | 角色 |
|---|---|---|---|
| Maco | OpenClaw（agnes） | `~/.npm-global/bin/openclaw` | 寫 code |
| Kim | OpenClaw（kimi instance） | 同上（唔同 config） | 寫測試 |
| Claude | Claude Code | `/usr/local/bin/claude` | code review |
| Codex | OpenAI Codex CLI | `~/.local/bin/codex` | security/perf review |
| Sheila | Hermes | `~/.local/bin/hermes` | 寫文檔 |

## 安裝步驟

### 1. OpenClaw（Maco + Kim 共用）

```bash
npm install -g openclaw
openclaw --version   # 驗證
```

- Maco 用默認 config（`~/.openclaw/openclaw.json`），agnes 模型。
- Kim 係獨立 instance，用 `~/.kimi_openclaw/openclaw.json`（kimi-coding 模型），靠環境變數 `OPENCLAW_CONFIG_PATH` 分隔。

### 2. Claude Code（Claude）

```bash
npm install -g @anthropic-ai/claude-code
claude --version    # 驗證
claude              # 首次行要登入授權
```

### 3. Codex CLI（Codex）

```bash
npm install -g @openai/codex
codex --version     # 驗證
codex login         # 首次行要登入授權
```

### 4. Hermes（Sheila）

```bash
# 按 Hermes 官方安裝指引
hermes --version    # 驗證
```

## 驗證

全部裝好後，跑一次流水線確認 5 個 agent 都通：

```bash
cd demo_agents && python3 run_demo.py
```

如果某個 agent 失敗，會喺 output 見到 `✗ <agent> 步驟失敗`，同埋 receipts 目錄會留低「上游做到邊一步」嘅 record——呢個正正係 receipt-bearing 交接嘅價值：**失敗可追溯，唔使由頭再跑**。
