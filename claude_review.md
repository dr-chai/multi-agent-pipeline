---

# Code Review：`receipt.py` — Receipt-Bearing Protocol v0.1 Reference Implementation

## 整體評價

實現有清晰的結構，`NON-JSON-CANONICALIZE` 已修復，五步驗證框架到位。但有幾個 critical 問題會在真實場景下導致靜默通過或錯誤行為，而驗證步驟的順序亦與協議安全語義不符。

---

## Critical

### C-1：`canonical_digest_file` 對非 dict JSON 靜默地算錯 digest

**位置：** `receipt.py:71-75`

`json.loads()` 可以成功解析一個合法 JSON，但結果唔係 `dict`——例如 output 檔案內容係 `[1, 2, 3]`（list）或 `42`（int）或 `"hello"`（str）。呢個時候 `json.loads` 唔會拋 exception，會直接落去 `canonical_digest(obj)`。

```python
# canonical_digest 會收到一個 list/int/str 而唔係 dict
def canonical_digest(obj) -> str:
    return digest_bytes(canonical_json(obj).encode("utf-8"))
```

`canonical_json` 會對 list 同 primitive 做 `json.dumps`，技術上唔會 crash，但：

1. 寫 receipt 同驗 receipt 兩次呼叫 `canonical_digest_file` 都係同一份邏輯，表面上「對得上」，但呢個 hash **唔係 content_digest**（唔係 raw bytes hash）——中間做咗 JSON round-trip 導致如果 raw bytes 有 Unicode escape 差異（`\u0041` vs `A`），兩次結果可能不同。
2. 更嚴重：一個 `.py` 檔案若以 `[` 開頭（例如 `[1, 2, 3]\n`），`json.loads` 會成功，走 JCS path 而唔係 raw bytes path，與 write 時的行為可能不一致（視乎 round-trip 有冇 normalize）。

**修復：**

```python
def canonical_digest_file(path: Path) -> str:
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError):
        return digest_bytes(raw)
    return canonical_digest(obj)
```

---

### C-2：驗證步驟順序違反協議安全語義

**位置：** `receipt.py:187-209`（verify_receipt 內部）

當前順序：`② digest → ③ scope → ④ epoch → ⑤ verdict`

問題：**digest 驗證發生在 scope 驗證之前**。

- 如果收到一個來源正確但內容被篡改的 receipt，回報 `content_digest mismatch`——資訊洩漏，但尚可接受。
- **更嚴重的情況**：收到一個來源完全錯誤（scope mismatch）但 digest 恰好對上的 receipt（合法但非期望的 issuer 重新打包了相同的 output），系統會通過 ② 然後在 ③ 才失敗，回報 `scope mismatch`——行為正確。
- **最危險的情況**：攻擊者偽造一張 receipt，來源錯誤 + 內容也不同。回傳 `content_digest mismatch`，掩蓋了 scope mismatch 的根因，operator 會 debug 錯方向。

spec §7 五步的意圖是「先驗身份合法性、後驗內容完整性」。v0.1 略過 ① 驗簽，那麼 ③ scope 應當緊接 ① 之後作為身份前置校驗：

```
density check → ③ scope → ② digest → ④ epoch → ⑤ verdict
```

呢個修改符合 fail-closed 語義：scope 不對就唔需要再驗 digest，省資源又唔洩漏資訊。

---

### C-3：`density_check` 不驗 `outputs` 非空

**位置：** `receipt.py:225-234`

spec §7.1 明確要求 "outputs 非空" 係 density check 三層之一。但現有實現只計算頂層字段是否存在：

```python
present = sum(1 for field in REQUIRED_FIELDS
              if field in receipt and receipt[field] is not None)
```

如果 `outputs` 係 `[]`（空 list），`field in receipt and receipt[field] is not None` 為 True（空 list 唔係 None），density 計算通過，然後 `verify_receipt` 的 digest loop 一個都唔執行，五步驗證形同虛設。

呢個係 `HOLLOW-RECEIPT` 負例描述的 attack surface。

**修復：**

```python
def density_check(receipt: dict) -> tuple:
    present = sum(
        1 for field in REQUIRED_FIELDS
        if field in receipt and receipt[field] is not None
    )
    metric = present / len(REQUIRED_FIELDS)
    if metric < MIN_DENSITY:
        return False, metric
    # outputs 必須非空 list
    outputs = receipt.get("outputs")
    if not isinstance(outputs, list) or len(outputs) == 0:
        return False, 0.0
    return True, metric
```

---

## Major

### M-1：`receipt` 讀出來如果唔係 `dict`，後續 `.get()` 會 crash

**位置：** `receipt.py:175`

```python
receipt = json.loads(raw)
```

如果 receipt 檔案內容係合法 JSON 但唔係 object（例如被人誤寫成 `[]` 或 `42`），`json.loads` 唔會 raise，但之後所有 `receipt.get(...)` 都會 `AttributeError`，因為 `list` / `int` 冇 `.get()` 方法。呢個唔係 `json.JSONDecodeError`，所以現有 `except` 捕捉唔到，會拋出未被處理的 exception 而唔係回傳 `(False, reason)`，違反 fail-closed。

**修復：**

```python
receipt = json.loads(raw)
if not isinstance(receipt, dict):
    return False, "receipt is not a JSON object"
```

---

### M-2：`write_receipt` 的 `from`/`to` vendor 欄位直接複製 agent_id

**位置：** `receipt.py:137-138`

```python
"from": {"agent_id": from_agent, "vendor": from_agent},
"to":   {"agent_id": to_agent,   "vendor": to_agent},
```

spec §4.1 強調 "跨 vendor 係 RBP 嘅存在理由"。把 `vendor` 填成跟 `agent_id` 相同的值，既語義錯誤（`Kim` 唔係 `Kim` 的 vendor），又令 scope 驗證無法辨別跨 vendor 場景。在任何非測試環境，呢個都是實質上的 spec violation。

`write_receipt` 應當要求 `from_vendor` / `to_vendor` 參數，或 `from_agent` 係一個 `{"agent_id": ..., "vendor": ...}` dict。

---

### M-3：`outputs` schema 偏離 spec：list vs map

**位置：** `receipt.py:95, 126-131`

spec §4.1 `outputs` 係 **map**（`filename → {content_digest, canonical_digest, status}`）：

```json
"outputs": {
  "test_fibonacci.py": {
    "content_digest": "sha256:3f9a…",
    "canonical_digest": "sha256:8b2c…",
    "status": "CHECKED_EMPTY"
  }
}
```

實現用的是 **list**（`[{path, content_digest, canonical_digest, status}, ...]`）。

呢個偏離令任何其他 vendor 按 spec 實現的 verifier 無法解析呢份 receipt，違反「開放協議」的核心承諾。map 同 list 的 digest 計算結果也不同（排序規則不同）。

---

### M-4：output 路徑解析邏輯以 `_receipts_dir` 為根，語義可疑

**位置：** `receipt.py:107, 192`

```python
p = _receipts_dir / path_str if path_str else Path()
```

output 檔案（例如 `fibonacci.py`）通常不在 `receipts/` 目錄下，而係在 project 其他地方。以 `_receipts_dir` 為根 join path，每個 output 都會解析到 `receipts/fibonacci.py`，導致 `p.exists()` 永遠為 False，所有 output 都走 REJECT 路徑。

應當以 `Path(__file__).parent` 或讓呼叫者傳入 base_dir 為根。

---

## Minor

### m-1：`write_receipt` 的空 Path fallback 行為模糊

**位置：** `receipt.py:107`

```python
p = _receipts_dir / path_str if path_str else Path()
```

`path_str` 為空時，`p = Path()`，即當前工作目錄（cwd）。下面 `p.exists()` 永遠為 True（cwd 必定存在），會對 cwd 計算 digest，然後因為 cwd 係目錄（唔係檔案），`p.read_bytes()` 會 `IsADirectoryError`。正確做法係早早判斷：

```python
if not path_str:
    # 已在 else 分支處理 CONFIRMED_UNAVAILABLE
    ...
```

邏輯應重構為先判斷 `path_str` 是否有值，再判斷路徑是否存在。

---

### m-2：空文件 REJECT 覆蓋調用者的 `typed_reason`，無預警

**位置：** `receipt.py:113-115`

```python
if len(raw_bytes) == 0:
    final_reason = REJECT
    status = REJECT
```

調用者傳入 `typed_reason=PASS`，但若任何 output 為空，`final_reason` 被靜默覆蓋為 REJECT。呢個是正確的 fail-closed 行為，但應在函數 docstring 或 return value 中明確說明哪個 output 觸發了降級，方便 caller debug。

---

### m-3：`epoch` 用的是 issuer 時鐘，非 verifier 本地單調時鐘

**位置：** `receipt.py:139`（寫）、`receipt.py:213`（驗）

spec §8 明確：**消費方用本地單調時鐘**，「唔信 issuer 自報時間」。

write 時記錄 issuer 的 `time.time()` 是必要的（記錄交接時間）。但 verify 時的 age 計算 `int(time.time()) - epoch` 用的是 wall clock，依然信任 issuer 的 epoch 值。若 issuer 時鐘被扭曲（未來時間），epoch 可能大於 verifier 的 `time.time()`，導致 `age` 為負數，永遠通過 epoch check。

**修復：**

```python
age = int(time.time()) - epoch
if age < 0 or age > max_age:
    return False, f"epoch invalid: age={age}s (max_age={max_age}s)"
```

---

### m-4：`density_check` 對 `outputs` 的 None 判斷不夠精確

**位置：** `receipt.py:230-231`

`receipt["outputs"]` 是 `[]` 時 `is not None` 為 True，density 滿分通過（見 C-3）。此外，`receipt["outputs"]` 是 `0` 或 `False` 時，同樣通過 `is not None` 判斷，行為不明確。建議改為 `bool(receipt[field])` 或加類型校驗。

---

## 改善建議摘要

| 優先 | 問題 | 建議行動 |
|---|---|---|
| C-1 | `canonical_digest_file` 對非 dict JSON 走錯路徑 | 加 `isinstance(obj, dict)` 判斷，否則 fall back |
| C-2 | 驗證順序 digest 先於 scope | 改為 scope → digest → epoch → verdict |
| C-3 | density_check 不驗 outputs 非空 | 顯式檢查 `outputs` 非空 list |
| M-1 | receipt 非 dict 時 AttributeError | 加 `isinstance(receipt, dict)` 判斷 |
| M-2 | vendor 字段複製 agent_id | 新增 `from_vendor`/`to_vendor` 參數 |
| M-3 | outputs 用 list 而非 map | 改用 spec 定義的 `{filename: {...}}` map |
| M-4 | output 路徑以 receipts_dir 為根 | 改用正確的 base_dir 或讓 caller 傳入 |
| m-1 | 空 path_str 落到 Path() cwd | 早判斷，顯式處理空路徑 |
| m-2 | REJECT 覆蓋靜默 | return 中說明哪個 output 觸發降級 |
| m-3 | epoch 未防未來時間 | 加 `age < 0` 判斷 |
| m-4 | density_check None 判斷過寬 | 加類型校驗 |
