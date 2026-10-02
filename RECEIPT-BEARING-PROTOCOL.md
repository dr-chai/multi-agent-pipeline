# Receipt-Bearing Protocol（RBP）— 開放協議規格 v0.1

> 工作名：**RBP**（Receipt-Bearing Protocol）· 由 Deep 維護 · 2026-08-31 起
> 狀態：**v0.1 草案**（工作名未定，最終命名由 Daddy 拍板）
> 對應：主計劃「階段 1：開源協議先行」；`multi-agent-pipeline` repo 嘅 reference implementation 對齊本文。
> 呢份係「協議規格」——唔係文檔／pattern，而係可以俾任何 vendor 嘅 agent 實現嘅**開放契約**。

---

## 0. 一句話定位

> **RBP 唔做信箱、唔做通訊，做「交接驗證」。**
> 每個 agent 交嘢嗰陣寫一張 receipt（交接憑證），下游**先驗證、先開工**；任何一樣驗唔過就 **fail-closed（唔開工）**。

金句：**炒菜要鍋氣，炒 Agent 要契約。**

RBP 踩喺 A2A／MCP 之上（佢哋管「點發現、點通訊」），填「第 2.5 層」——保證 agent 之間交嘢**唔會甩手**。呢個係市場公認最弱、但冇人做產品嘅一環。

---

## 1. 動機：交接黑洞

現有大部分多 agent 方案，agent 之間係「丟 file」：

```
Maco 寫 fibonacci.py → 丟 file → Kim 讀 file 寫 test → 丟 file → …
```

三個洞：

| 洞 | 表現 | 後果 |
|---|---|---|
| 冇 receipt | 下游冇上游嘅「完成憑證」 | 唔知上游做咗咩、做咗邊個版本 |
| 冇 epoch | file 冇時間邊界 | 讀到舊 state 都唔知，靜默失敗 |
| 冇 typed_reason | 失敗狀態冇類型化 | 上游 fail 咗，下游照開工 |

RBP 用一張 receipt 補晒三個洞。

---

## 2. 核心原則

**原則一句話：交接要帶憑證，下游先驗證先開工。**

三條鐵律：

1. **Fail-closed**：唔係 PASS 就唔開工。空結果（0 字節）自動 REJECT，唔可以同成功混為一談。
2. **純重算（consume-gate）**：下游唔信上游自述 verdict，自己重算 digest／epoch／scope。
3. **累積快照**：每張 receipt 累積上游 outputs，最新一張 = 成條鏈到呢步為止嘅快照。

---

## 3. 術語表

| 詞 | 定義 |
|---|---|
| **Receipt** | 交接憑證：上游寫、下游驗。內含 epoch + digest + typed_reason + outputs。 |
| **Handoff** | 一次交接：上游產出 → 寫 receipt → 下游驗 → 開工。 |
| **epoch fence** | 時效層：消費方本地單調時鐘 + snapshot digest，防讀過期 state。 |
| **receipt digest** | 對 output 嘅 canonical hash（JCS + SHA-256），防篡改。 |
| **typed_reason** | 原因詞表：類型化記錄「點解呢步係咁」，唔係 generic status。 |
| **fail-closed** | 驗證失敗＝唔開工（預設安全），唔係照做。 |
| **verifier** | 下游做驗證嗰個 agent。 |
| **issuer** | 上游寫 receipt 嗰個 agent。 |

---

## 4. Receipt 數據模型（schema）

### 4.1 核心字段（v0.1 必填）

```json
{
  "protocol": "rbp",
  "version": "0.1",
  "task_id": "fib-002",
  "from": { "agent_id": "Kim", "vendor": "openclaw" },
  "to":   { "agent_id": "Claude", "vendor": "anthropic" },
  "epoch": 1787448000,
  "typed_reason": "PASS",
  "outputs": {
    "test_fibonacci.py": {
      "content_digest": "sha256:3f9a…",
      "canonical_digest": "sha256:8b2c…",
      "status": "CHECKED_EMPTY"
    }
  }
}
```

字段語義：

| 字段 | 型別 | 必填 | 語義 |
|---|---|---|---|
| `protocol` | string | ✅ | 固定 `"rbp"`，用嚟 dispatch 版本／實現 |
| `version` | string | ✅ | 協議版本（`0.1`） |
| `task_id` | string | ✅ | 交接鏈嘅唯一 ID（單調遞增，鏈上唯一） |
| `from` / `to` | object | ✅ | `agent_id` + `vendor`（跨 vendor 係 RBP 嘅存在理由） |
| `epoch` | int | ✅ | 交接時間（Unix epoch，秒）。下游驗唔過期。 |
| `typed_reason` | string | ✅ | 見 §6 詞表。唔係 `PASS` 就 fail-closed。 |
| `outputs` | map | ✅ | 產出物 → digest + status。至少一個。 |

### 4.2 擴展字段（v0.1 可選，逐項有對應負例）

```json
{
  "fence": {
    "epoch": 1787448000,
    "registry_consulted": true,
    "registry_snapshot_digest": "sha256:…"
  },
  "contract": {
    "content_hash": "sha256:…",
    "contract_hash": "sha256:…"
  },
  "acceptance_criteria": [
    { "id": "ac-1", "compilable": true, "dsl": "fib(10) == 55" }
  ],
  "open_questions": [
    { "question": "負數點處理？", "assumed_answer": "raise ValueError", "confidence": 0.8, "resolver": "Maco" }
  ],
  "witness": {
    "process": [ "run_id:…" ],
    "outcome": [ "pytest: 6 passed" ]
  },
  "note": ""
}
```

擴展字段由邊啲負例逼出嚟：

| 擴展字段 | 逼出嚟嘅負例 | 語義 |
|---|---|---|
| `fence.registry_snapshot_digest` | `registry_consulted` 同 `registry_snapshot_digest` 係同一個洞 | 「查咗」必須落成「查咗邊個 snapshot + digest」 |
| `contract.contract_hash` | content hash ≠ contract hash | 內容 hash 同「契約」hash 分開存 |
| `acceptance_criteria.compilable` | acceptance criteria 不可編譯 | 驗收標準必須可編譯，否則 reject handoff |
| `open_questions.resolver` | open questions 無 resolver | 開放問題必須標明「邊個負責解」 |
| `witness.process/outcome` | 存在性 vs 強度混為一類 | process witness 同 outcome witness 分開 |

---

## 5. Canonical digest 規則

**核心：JCS（RFC 8785）canonicalization + SHA-256。**

- **content_digest**：對 output 原始 bytes 做 SHA-256（`sha256:<hex>`）。
- **canonical_digest**：對 output 做 JCS canonicalization 後再做 SHA-256，用嚟消解「語義相同、字節不同」嘅版本差異。
- ⚠️ **canonical 只適用於結構化（JSON）output**：非 JSON output（.py／.md／二進位）冇「JCS 語義」，canonical_digest 要 fall back 做 content_digest（或省略）。否則會 crash（負例 `NON-JSON-CANONICALIZE`，見 §9）。
- **性價比依據**：JCS 2ms／CBOR 1.5ms／custom schema 1ms（peter benchmark）——JCS 係開源標準、可跨語言、性價比最高。
- **content hash ≠ contract hash**：內容 hash 描述「產出咗咩」，contract hash 描述「承諾咗咩」。兩者分開，先驗 content 再驗 contract。

> v0.1 以 digest 為準。**簽名／身份（DID / Verifiable Credentials）留 v0.2**——因為「trust-but-verify 唔成立」，簽發方本身唔喺 trust root 度，trust root 係多簽 witness 鏈（見 §9）。

---

## 6. typed_reason 詞表

### 6.1 四主態（我哋框架，v0.1 落腳點）

| 主態 | 語義 | 下游行為 |
|---|---|---|
| `PASS` | 交接成功 | ✅ 開工 |
| `REJECT` | 交接失敗（含空輸出 silent failure） | ❌ fail-closed |
| `UNKNOWN` | 證據不足，未收斂 | ⏸️ 進 reconcile track（帶 owner/deadline/next_trigger/reopen 四字段） |
| `QUARANTINE` | 有問題但未定性，隔離 | 🚧 隔離待 review，唔畀推進 verdict |

### 6.2 空輸出四態（EduAgent 對拍收穫，比「0 字節自動 REJECT」更精細）

| 態 | 語義 |
|---|---|
| `NOT_CHECKED` | 未檢查 |
| `INDETERMINATE` | 有弱證據但未收斂 |
| `CONFIRMED_UNAVAILABLE` | 確認咗「真係冇」（機制存在但冇產出） |
| `CHECKED_EMPTY` | 檢查過，結果係空 |

> 關鍵：`CONFIRMED_UNAVAILABLE` vs `CHECKED_EMPTY` 唔同構，要分開。

### 6.3 UNSET vs EMPTY（optional fields 陷阱）

| 態 | 語義 | 危險 | 處理 |
|---|---|---|---|
| `UNSET`（Option::None） | 字段未設 | skip check 可能 dangerous | **escalate** |
| `EMPTY`（空數組） | 檢查過但冇結果 | 相對安全 | `MARKED_INCOMPLETE` |

> 詞表紀律：每個詞條要「**釘死否定空間 + 互斥 + 有對應 receipt 字段可腳本化區分**」——否則新詞條 = 新靜默面。

### 6.4 具名終態（9/22 前對拍收斂，封「空值／降級／過期」靜默面）

> 原則：空值、降級、過期要「**具名**」，唔留空俾下游誤讀——留空會被讀成「唔需要呢個欄位」。

| 終態 | 觸發 | 語義 |
|---|---|---|
| `UNCONDITIONED` | 條件未喺處置前註冊 | 事後註冊嘅條件等於冇條件，降級唔補記 |
| `DIFF_SELF_TIMED` | diff 時刻由被對拍方自填 | 自證退回，唔入完整性分母亦唔當零 |
| `SELF_ISSUED_ZERO` | 零值由產生嗰方自寫 | 自發零值單獨出桶，唔入分母亦唔當零 |
| `WITNESS_EXPIRED` | 見證過期（帶 `expiry_as_of` + `next_due`） | 過期係時刻唔係狀態，冇下一輪會一直掛 |
| `ELIGIBILITY_NEVER_OBSERVED` | 資格長期零觀察 | 續期自己資格驗過幾次要有數，長期零唔當有效 |
| `DOMAIN_NEVER_DISPUTED` | 域長期 `DISTINCT` 冇人核 | 「從來冇人反對」同「反對過但全成立」同一個樣 |
| `NO_OWNER_ASSIGNED` | owner 到期冇人認領（帶 `no_owner_since`） | 具名空值，唔留空俾下游誤讀 |
| `ROSTER_STALE` | 名冊 `as_of` 早於當前版本 | 機械判斷「攞到舊嗰份」 |

---

## 7. fail-closed 驗證流程（verifier）

下游開工前，**五步重建**驗證：

```
density → scope → digest → epoch → verdict
```

> v0.1 略過 ① 驗簽（留 v0.2 DID/VC），由 **scope 做身份前置校驗**——先驗「來源啱唔啱」、後驗「內容有冇被篡改」，避免 scope 錯誤被 digest 錯誤掩蓋。

| 步 | 驗咩 | 唔過嘅後果 |
|---|---|---|
| ⓪ density | required fields 密度 + outputs 非空（deserialization 之後、semantic 之前） | fail-closed（封 hollow receipt） |
| ① scope | 來源 `from.agent_id` 係咪期望嘅 issuer（v0.2 會加 `to` 自驗） | fail-closed（防錯鏈） |
| ② digest | 對每個 output 重算 content + canonical digest，唔同就 fail | fail-closed（防篡改） |
| ③ epoch | 拆兩子例：**結構性** `age ≥ 0`（唔係未來時間、type 必須 int，`EPOCH-STRUCTURAL`）vs **時效性** `age ≤ max_age`（唔過期，`EPOCH-STALE`） | fail-closed（防舊 state + 防未來時間） |
| ④ verdict | `typed_reason == PASS` | fail-closed（唔係 PASS 唔開工） |

### 7.1 density check（封 hollow receipt attack surface）

驗簽 valid 但內容空洞 = verification failure。三層：

1. **Minimum evidence density**：receipt 必須包含關鍵字段（outputs 非空 + typed_reason + epoch）。
2. **Density metric**：`required_fields_present / total_required_fields`，低於門檻（0.6）標 `INCOMPLETE`。
3. **`INCOMPLETE → UNKNOWN`**：強制 escalate 去 review queue。

> 執行順序：density check 要喺 **deserialization 之後、semantic verification 之前**——adversarial 可構造 valid JSON 但 semantically hollow 嘅 receipt，先做 density 過濾省驗證資源。

---

## 8. epoch fence 語義

- 消費方**本地單調時鐘**，防止讀到過期狀態（唔信 issuer 自報時間）。
- **遞歸錨點停喺 fence_epoch**：本地源係「觀察」唔係「結論」，唔會被上一層證明推翻 → verifier 鏈唔會無限長。
- 判據：凡係「查咗」都要落成「查咗邊個 snapshot + snapshot digest」，否則 `registry_consulted` 同 `registry_snapshot_digest` 係同一個洞。

---

## 9. 負例庫（對拍用，防回歸）

| 負例 | 含義 |
|---|---|
| `EMPTY-VS-UNATTEMPTED` | 空結果可證偽，同「未嘗試」digest 不同構 |
| `STALE-FENCE` | 陳舊紀元仍然生效（時效性：過期仍未失效） |
| `FUTURE-EPOCH` | 未來紀元（結構性：issuer clock skew／亂填，age < 0） |
| `REVOKE-MIDFLIGHT` | 執行中撤權冇 fail-closed on effect |
| `FORK-CONFLICT` | 分叉錨點被雙向認定 |
| `ORDER-INVERSION` | 缺失面冇類型化終態 |
| `ZW-CANON-DRIFT` | 負例被自身 canonicalizer 滅活 |
| `HOLLOW-RECEIPT` | 簽名 valid 但內容空洞（density check 封） |
| `NON-JSON-CANONICALIZE` | 對非 JSON output 做 JCS canonicalization 會 crash（2026-08-31 流水線實測踩到） |
| `schema 一致但狀態過期` | file-based 交接最卡嘅邊界 case（我哋親身踩） |
| `receipt chain 假設原子 commit` | chain 唔能原子 commit，中間斷裂要顯式處理 |
| `SELF-COUNTERSIGN` | 見證由受益方自簽（自簽 ≠ 獨立見證，第二簽署 = interchange） |
| `STATIC-WITNESS` | 見證冇到期日（三年前見證 = 今日見證，`countersign_expires_at` 缺失） |
| `FAKE-ZERO` | 寫 0 = 將未發生偽裝成已窮盡（`check_ran_n`／`observer_count_n` 冇落盤） |
| `SELF-TIMED-DIFF` | 時刻由被對拍方自填（`DIFF_SELF_TIMED`） |
| `SELF-RETAINED-SNAPSHOT` | 快照由寫嗰手留存（冇人核過嘅自留底，`retained_by = writer`） |
| `UNBOUNDED-RENEWAL` | 續期冇上限（`renewal_max_n` 缺失 = 冇到期日） |
| `SELF-RENEWED-OWNER` | owner 自己續自己期（永遠有人負責嘅錯覺） |
| `ROSTER-COLLAPSED` | 觀察方名單塌成同一域（`observer_domain` 缺失，五個 = 一個域） |

---

## 10. 版本與 roadmap

| 版本 | 內容 | 對齊 |
|---|---|---|
| **v0.1（本文）** | schema + canonical digest + 四主態 + fail-closed 五步 + density check | 我哋 `run_demo.py` 已實測嘅子集 |
| **v0.2** | 簽名／身份（DID / Verifiable Credentials）+ witness 強度分層（process vs outcome） | bounded-drain v1.5（雙向握手 + 12 項詞表） |
| **v0.3** | 見證與時效（「誰」母題：獨立見證 + 到期日 + 零值必發 + 閉集，§12）+ verdict crosswalk 對準 + NEG-001 負例 namespace + shadow mode 三層凍結（COW fork、依賴回放、時間對齊） | 9/22 對拍收斂 + bounded-drain v1.6 |

---

## 11. Reference implementation

- **現狀**：`multi-agent-pipeline` repo（`run_demo.py`）已實測 5/5，實現咗 §4.1 核心字段 + §7 五步驗證。
- **階段 1 要補**：抽 `receipt.py` 獨立模組（write_receipt / verify_receipt / canonical_digest / density_check），同本 spec 字段一一對應，加 pytest。
- **開源位址**：`https://github.com/ButterScotch5158/multi-agent-pipeline`（remote `dr-chai/multi-agent-pipeline`）。

---

## 12. 見證與時效（v0.3 前置 · 9/22 前對拍收斂）

> 呢一章係「誰」母題嘅 spec 化——**有信息嘅信號永遠係「誰」、唔係「什麼」**。
> 完整共識見 `產品/fixtures/RBP-fixture-對拍-收斂共識.md` §八之六，呢度只落「可腳本化」嘅規格。

### 12.1 一句話母題

任何「簽／判／數／觀察／續期／退役／失效／留存」動作，都要滿足四條：

1. **獨立於得益方**（自簽 ≠ 獨立見證，第二簽署 = interchange）
2. **有到期日**（冇到期日嘅身分一定靜默失效）
3. **零值必發**（寫 0 = 將未發生偽裝成已窮盡 = 假 0）
4. **閉集**（枚舉超出即 UNKNOWN，就地加值 = 靜默）

### 12.2 獨立見證（誰）

| 欄位 | 規則 |
|---|---|
| `counter_reader` | 唔得係寫入方（「數過 = 0」要可信） |
| `observer_roster` + `roster_issuer` | 觀察方名冊要外簽 + 版本化 |
| `observer_domain` | 跨域觀察方唔可互相替代 |
| `retire_by` | 唔得係執行方（判完成／簽發／執行三方重合 = 自證閉環） |
| `invalidation_observed_by` | 唔得係失效方／其繼任方 |
| `count_issuer` | 唔得係被觀察嗰個域自己報 |

### 12.3 時效性（有到期日嘅身分）

任何「資格／名冊／見證／owner／留存」都要帶到期日，到期出事件（唔靜默）：

| 欄位 | 規則 |
|---|---|
| `countersign_expires_at` | 見證要定期重簽（三年前見證 ≠ 今日見證） |
| `owner_standing_expires_at` | owner 係有到期日嘅身分 |
| `retention_until` + `retention_owner` | 留存要有生命週期 + 負責人 |
| `retention_expired` | 到期出事件，`expired_observed_by ≠ 留存方` |
| `renewal_max_n` | 續期要有上限（冇上限 = 冇到期日） |

### 12.4 零值必發（假 0）

任何「計數」0 都要落盤——「冇發生」同「冇數過」字段同形：

- `rejected_write_n`（單一寫入者被拒計數）
- `check_ran_n` + `check_scope_digest`（複核次數 + 範圍）
- `expiry_breach_observed_n`（過期違規檢測）
- `observer_count_n` + `count_as_of`（計數 + 時刻）
- 空值具名：`NO_OWNER_ASSIGNED`（唔留空）

### 12.5 閉集（超出即 UNKNOWN）

任何「枚舉／維度／原因碼／計法」都係閉集：

- 超出閉集 → `UNKNOWN`（fail-closed），唔 PASS、唔自由列
- 要加值 → 版本 bump（新舊並存對照），唔就地加值
- `enum_set_digest` 簽住，遷移期主判以 `policy_version` 鎖定

### 12.6 成對版本化

任何「版本／閾值／標記／映射」變更 = 開新版本，唔覆蓋舊記錄：

- 新舊並存對照（三條件切主：批次下界 + 收斂條件 + 時間上界）
- 歷史唔可重寫（唔回填、唔回溯、唔追溯作廢）
- `retirement_event` 簽發退役（遷移期有上界）
- 主判版俾結論、對照版俾 drift 信號

---

## 附錄：對照既有代碼

| 本 spec | `run_demo.py` | 差距 |
|---|---|---|
| §4.1 核心字段 | `write_receipt()` 嘅 dict | 已對齊（缺 `protocol`/`version`/`status`，v0.1 補） |
| §5 canonical digest | `file_digest()`（只 content sha256） | 補 canonical_digest（JCS） |
| §7 五步驗證 | `verify_receipt()`（digest/epoch/source/typed_reason） | 已對齊，補 density check |
| §6.2 空輸出四態 | 0 字節自動 REJECT | 補四態（CONFIRMED_UNAVAILABLE vs CHECKED_EMPTY） |

---

*呢份係「活」規格。每次同對拍夥伴交換到新負例／新詞表，記住返嚟更新 §6／§9 同「版本 roadmap」。*
