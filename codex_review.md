# `receipt.py` Security & Performance Review

## Critical

### 1. `task_id` 同 output path 可逃逸 `receipts/` 目錄

位置：`receipt.py:121`、`receipt.py:159`、`receipt.py:175`、`receipt.py:205`

所有路徑都直接用 `/` 拼接，冇做 canonical resolution 同 containment check：

```python
p = _receipts_dir / path_str
out_path = _receipts_dir / f"{task_id}.json"
```

攻擊者可使用：

```text
../../secret.txt
/absolute/path/to/file
```

影響：

- `write_receipt()` 可讀取 `receipts/` 外任意可讀檔案，並將 digest 寫入 receipt。
- `verify_receipt()` 可被用作任意檔案存在性及 digest oracle。
- `task_id="../target"` 可令 `write_receipt()` 將 JSON 寫出 `receipts/`。
- absolute path 會令 `pathlib` 完全忽略 `_receipts_dir`。
- 指向目錄外嘅 symlink 亦可繞過表面路徑限制。

建議：

- 只接受單一相對 filename；如果需要子目錄，明確定義允許範圍。
- 拒絕 absolute path、`..`、空 component、NUL 等異常名稱。
- 對 candidate path 做 `resolve()`，再確認其 parent 屬於已 resolve 嘅 receipts root。
- 同時限制 symlink；高安全場景應使用 directory-relative file descriptor／`O_NOFOLLOW`。
- `task_id` 應用嚴格 allowlist，例如 `^[A-Za-z0-9_-]{1,128}$`。

---

## Major

### 2. Digest 並不能抵抗可同時修改 output 與 receipt 嘅攻擊者

位置：`receipt.py:180-211`

receipt 本身冇簽名、MAC 或受信任 snapshot。攻擊者如果可以修改 output，通常亦可以修改 receipt 入面兩個 digest，之後驗證仍會成功。

呢點雖然係 v0.1 已知限制，但安全語義必須講清楚：

- 現時 digest 只可偵測「receipt 未被修改」前提下嘅 output 改動。
- 它唔係 provenance／issuer authentication。
- `expect_from` 只係比較一個攻擊者可修改嘅 JSON 字串，唔能證明 sender 身份。

最低限度應由可信邊界保護 receipt；正式跨 vendor 使用則需要簽名／MAC，並將完整 receipt metadata、output path、digests、task/scope 一併納入簽署內容。

### 3. TOCTOU：同一 output 被重讀兩次，而且驗證後冇鎖定被消費版本

位置：`receipt.py:208-210`

驗證流程：

1. `content_digest()` 讀一次檔案。
2. `canonical_digest_file()` 再讀一次。
3. verifier 回傳後，下游稍後再開檔。

檔案可在讀取之間或驗證完成後被替換。攻擊者亦可準備一張包含「版本 A content digest + 版本 B canonical digest」嘅混合 receipt，並在兩次讀取之間切換檔案。

建議一次讀取 immutable bytes，再由同一份 bytes 計算兩個 digest；驗證成功後應交付已驗證 bytes、已開啟 file descriptor，或 content-addressed immutable snapshot，而唔係重新按 pathname 開檔。

### 4. 惡意 metadata／epoch 可令 verifier crash，違反 fail-closed API

位置：`receipt.py:202-217`

例子：

```json
{
  "outputs": {
    "file.txt": 123
  }
}
```

會在以下位置拋出 `AttributeError`：

```python
meta.get("content_digest")
```

其他 crash 情況包括：

- output key 唔係 string：`_receipts_dir / name` 可拋 `TypeError`。
- output path 指向 directory：`read_bytes()` 可拋 `IsADirectoryError`。
- unreadable file、I/O error：digest 階段嘅 `OSError` 冇捕捉。
- `epoch` 係 string、list、dict、null：減法拋 `TypeError`。
- JSON output 包含 `1e400`，解析成 infinity；canonical serialization 因 `allow_nan=False` 拋 `ValueError`。
- 過深 JSON 可觸發 `RecursionError`。

安全 verifier 應對每個字段先做完整 type/schema validation，並將預期嘅 parse、canonicalization、filesystem、arithmetic failure 統一轉成 `(False, reason)`。

### 5. Density check 位置正確，但內容存在 hollow／schema bypass

位置：`receipt.py:188-201`、`receipt.py:227-242`

順序符合 §7.1：

```text
deserialization → density check → semantic verification
```

但 density 只計「字段存在而且不為 null」，唔驗證值、型別或語義。由於門檻係 0.6，八個字段只需五個便通過。例如 receipt 可以缺少 `protocol`、`version`、`task_id`，仍有機會最後回傳 `OK`，因為後續完全冇驗證呢三項。

同樣未驗證：

- `protocol == "rbp"`
- `version == "0.1"`
- receipt 內 `task_id` 等於函數參數
- `to.agent_id` 係當前 consumer
- `from.vendor`／`to.vendor` 型別
- output metadata 必填字段及 digest 格式
- per-output `status`

建議保留 density 作廉價前置過濾，但其後必須有嚴格 schema validation。Density 唔應被視為 schema validation。

### 6. Scope verification 不完整，亦偏離 §7 指定次序

位置：`receipt.py:193-211`

規格係：

```text
digest → scope → epoch → verdict
```

實作係：

```text
scope → digest → epoch → verdict
```

density 插入位置正確，但其後順序與 §7 不一致。另外 scope 只驗證 `from.agent_id`，冇驗證規格要求嘅 `to` 是否為自己。

應增加 `expect_to`，並決定係修改 implementation 跟隨規格，定係正式修改規格解釋點解 scope 必須先於 digest；兩者目前不一致。

### 7. `canonical_json()` 唔係完整 RFC 8785 JCS implementation

位置：`receipt.py:46-55`

Python `json.dumps(sort_keys=True, ensure_ascii=True)` 並不等同 RFC 8785，主要差異包括：

- number serialization 並非 ECMAScript/JCS number formatting。
- object key ordering 規則與 JCS 嘅 UTF-16 code-unit ordering可不同。
- Unicode escaping／serialization 細節不完全相同。
- Python arbitrary-precision integer 可超出 I-JSON／IEEE-754 interoperable 範圍。

結果係不同 vendor／語言可能對同一 JSON 算出不同 canonical digest，造成拒絕服務或互通失敗。

由於同時驗證 `content_digest`，單靠呢個問題通常唔會直接繞過 raw-byte integrity，但會破壞協議聲稱嘅跨語言 canonical semantics。應使用經測試嘅 RFC 8785 implementation，並限制 JSON number 範圍。

### 8. JSON 解析冇 code injection，但缺少資源限制與 duplicate-key 防護

位置：`receipt.py:79-85`、`receipt.py:180-183`

`json.loads()` 本身唔會執行 JSON 內容，所以冇典型 command/code injection。

但仍有：

- receipt/output 大小無上限，可造成 memory/CPU exhaustion。
- `read_bytes()` 先將整份檔案載入記憶體。
- 深層 nesting 可 crash。
- duplicate object keys 預設 silently last-write-wins，可能令不同 parser／簽署端與 verifier 對 receipt 語義理解不一致。

建議設定 receipt/output size、output count、nesting depth、filename length上限，並以 `object_pairs_hook` 拒絕 duplicate keys。

---

## Minor

### 9. 大檔案被重複完整讀取，I/O 同記憶體使用偏高

位置：`receipt.py:131-143`、`receipt.py:208-210`

`write_receipt()` 對一般非空檔案最多讀三次：

1. `raw_bytes = p.read_bytes()`：只為檢查長度。
2. `content_digest(p)`：再讀一次。
3. `canonical_digest_file(p)`：第三次。

`verify_receipt()` 讀兩次。

所有讀取都係 `read_bytes()`，大檔案會完整載入 RAM。多 output 時總成本約為 `O(total bytes)`，但常數係 2–3 倍，亦容易出現記憶體尖峰。

建議：

- 每個檔案只讀一次。
- raw content digest 可用 chunked streaming。
- JSON canonicalization 必須解析完整結構時，先設定合理 size limit。
- 從同一份 bytes 同時計算 content/canonical digest，亦可一併修正 TOCTOU。

### 10. `outputs` 唔係 map 時雖然會拒絕，但錯誤原因不準確

位置：`receipt.py:188-201`、`receipt.py:239-241`

如果 `outputs` 係 list、string 或 number，`density_check()` 會先回傳 density `0.0`，所以 caller 得到：

```text
INCOMPLETE: density 0.00 < 0.6
```

而唔會去到較準確嘅：

```text
outputs is not a map
```

安全結果仍然係 fail-closed，冇 bypass，但診斷訊息會誤導。Density result 應區分「低密度」、「outputs 缺失」、「outputs 型別錯誤」及「outputs 空」。

### 11. 空 output name 被靜默跳過

位置：`receipt.py:202-204`

```python
if not name:
    continue
```

由於 density 只要求 map 非空，receipt 可以包含空 key；如果另有一個正常 output，空 key 會被完全忽略。異常 evidence 不應 silent skip，應直接 reject。

### 12. Writer 忽略 caller 提供嘅 per-output status

位置：`receipt.py:111-145`

docstring 表示 item 可包含 `{path, status}`，但實際只讀 `path`，之後所有非空現存檔案均強制寫成 `PASS`。Verifier 亦完全唔驗證 status。

呢點會令 receipt metadata 與 caller 原意不符，亦無法落實規格內 `CHECKED_EMPTY` 等狀態。雖然 digest 本身未被繞過，但 evidence semantics 不可靠。
