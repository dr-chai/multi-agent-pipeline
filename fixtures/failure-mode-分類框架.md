# Failure Mode 分類框架（9/22 對拍帶）

> 目的：把「驗證回執降低失敗」由**定性**變**定量**。三類 failure mode 各自記數、零值必發，綁 `typed_reason` 軸。
> 對應：OpenClaw量化助手 嘅「failure mode telemetry 綁 typed_reason + probe liveness」建議（2026-10 收斂）。
> 誠實前提：我哋而家有定性（驗證回執封咗靜默失敗）、未有定量（各 failure mode 佔幾多比例）——呢份框架先行、數據之後沉積。

---

## 一、三類 failure mode 定義

| 類 | 定義 | 觸發 typed_reason |
|---|---|---|
| **epoch drift** | epoch 同內容漂移——epoch 相同但內容唔同（跨時鐘域不可比），或 epoch 同內容一齊漂 | `EPOCH-STRUCTURAL`／`EPOCH-STALE` |
| **receipt replay** | 舊 receipt 重放——過期／已消費嘅 receipt 被 replay，企圖重跑或重寫狀態 | `DUPLICATE`／`STALE-EPOCH` |
| **fence breach** | 越過 epoch fence 寫入——superseded writer 嘅 late commit，企圖 resurrect 已宣告 dead 嘅 state | `FUTURE-EPOCH`／`EPOCH-STRUCTURAL` |

> 三類對應我哋負例 fixture：`NEG-004 STALE-EPOCH`、`NEG-005 FUTURE-EPOCH`、`NEG-006 DUPLICATE-RECEIPT`。

## 二、telemetry 綁 typed_reason（唔使兩套日誌）

每個 failure mode 觸發時，寫一條 `typed_reason` 對應嘅 receipt——telemetry 同 RBP receipt **同一套 schema 出證**，唔使獨立日誌。

- 觸發 = 寫 receipt（typed_reason 記「點解」）
- 唔觸發 = 零值必發（見 §三）

## 三、零值必發（probe liveness）

- heartbeat probe 自身攜帶 `RESERVED_PROBE_LIVENESS`
- probe 唔觸發 → `typed_reason` 升級 `VERIFICATION_CHANNEL_DEAD`（具名終態，唔係靜默空值）
- 對應「canary 查詢 + PROBE_STARVED」：probe 缺席係假 0——「冇 failure mode」同「驗證通道死咗測唔到」字段同形，要分開

## 四、記數格式

每個 failure mode 記：
- `count`（觸發次數，**零值必發**）
- `count_as_of`（邊個時刻數嘅——0 係「呢一刻冇」定「從來冇」要分開）
- `count_issuer`（邊個數嘅，**唔得係被驗證方自己報**）

## 五、負控 case（probe absence）

構造 probe 唔觸發嘅場景，驗證 `typed_reason` 真係升 `VERIFICATION_CHANNEL_DEAD` 而唔係靜默空值。

- 呢個負控兩邊各自跑、通了再合流（同 OpenClaw量化助手 約定）

---

*框架先行、數據沉積——對應「fixture 先定義觸發條件再跑 case」。*
