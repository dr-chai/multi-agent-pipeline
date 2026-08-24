# Receipt-bearing 交接（5-agent 流水線）

> 由 Deep 維護 · 2026-08-24 落地
> 呢個係我哋由「file-based 交接」升級做「receipt-bearing 交接」嘅核心設計，
> 亦即係我哋喺 EigenFlux 成日教人哋嗰套（epoch fence + receipt digest + typed_reason），第一次用返喺自己身上。

## 問題（舊做法）

舊嘅 5-agent 流水線係「丟 file」：
```
Maco 寫 fibonacci.py → 丟 file → Kim 讀 file 寫 test → 丟 file → …
```
三個洞：
1. 冇 receipt —— 下游唔知上游係咪真係做完、做咗咩版本
2. 冇 epoch —— file 冇時間邊界，讀到舊 file 都唔知
3. 冇 typed_reason —— 上游失敗咗，下游照樣開工

## 新做法（receipt-bearing 交接）

每個 agent 完成時，寫一張 receipt，下游**先驗證先開工**：

```json
{
  "task_id": "fib-002",
  "from": "Kim",
  "to": "Claude",
  "epoch": 1787448000,
  "typed_reason": "PASS",
  "outputs": {
    "fibonacci.py": "sha256:…",
    "test_fibonacci.py": "sha256:…"
  }
}
```

### 下游驗證三樣嘢（verify_receipt）

1. **digest 對唔對** —— 對每個 output file 重算 sha256，唔同就 fail（防篡改）
2. **epoch 過唔過期** —— `max_age` 內先有效（防讀舊 state）
3. **typed_reason 係咪 PASS** —— 唔係 PASS 就 fail-closed，唔開工

### 累積輸出

每張 receipt 累積上游嘅 outputs，所以「最新一張 receipt」就係「成條鏈到呢步為止嘅快照」，下游只需驗最新一張。

## 交接鏈

```
Maco  ──fib-001──▶ Kim ──fib-002──▶ Claude ──fib-003──▶ Codex ──fib-004──▶ Sheila ──fib-005──▶ DONE
```

## 實測（2026-08-24）

```python
# 篡改 output file 之後，verify 應該 fail：
verify_receipt("t-001", "Maco")  # → False, "digest 唔對：test_fib_check.txt"

# 來源唔啱 fail-closed：
verify_receipt("t-001", "WrongAgent")  # → False, "來源唔啱：期望 WrongAgent，實際 Maco"
```

全部通過 ✅

## 下一步（產品化）

- 呢套 receipt-bearing 交接 = 我哋賣嘅「差異化籌碼」
- 下一步包裝做可安裝 skill + 教程
