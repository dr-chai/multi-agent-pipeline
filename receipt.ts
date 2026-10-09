/**
 * Receipt-Bearing Protocol (RBP) — TypeScript (Node.js) reference implementation v0.1
 * Pure standard library (node:crypto, node:fs, node:path), zero third-party deps.
 *
 * The one hard interop requirement is canonical digest:
 *   sha256(JCS(value))   where JCS = RFC 8785 JSON Canonicalization Scheme.
 * Conformance: reproduce the golden vectors in fixtures/jcs-vectors.json.
 *
 * Known JS limitation: JSON integers beyond 2^53 lose precision when parsed
 * with JSON.parse, so the `numbers` golden vector's `big` field cannot be
 * reproduced byte-for-byte in JS (Python preserves it). Every other vector
 * passes. See fixtures/README.md.
 */

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, openSync, fsyncSync, closeSync, renameSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// ── typed_reason 詞表 ──────────────────────────────────────────────
export const PASS = 'PASS';
export const REJECT = 'REJECT';
export const UNKNOWN = 'UNKNOWN';
export const QUARANTINE = 'QUARANTINE';

export const NOT_CHECKED = 'NOT_CHECKED';
export const INDETERMINATE = 'INDETERMINATE';
export const CONFIRMED_UNAVAILABLE = 'CONFIRMED_UNAVAILABLE';
export const CHECKED_EMPTY = 'CHECKED_EMPTY';

export const UNSET = 'UNSET';
export const EMPTY = 'EMPTY';

export const REQUIRED_FIELDS = [
  'protocol', 'version', 'task_id',
  'from', 'to', 'epoch',
  'typed_reason', 'outputs',
];
export const MIN_DENSITY = 0.6;

// ── 目錄 ────────────────────────────────────────────────────────────
const receiptsDir = join(dirname(fileURLToPath(import.meta.url)), 'receipts');
mkdirSync(receiptsDir, { recursive: true });

// ── JCS（RFC 8785）string escape ───────────────────────────────────
// 逐個 UTF-16 code unit escape：控制字符 + 所有非 ASCII → \uXXXX（小寫 hex）。
// 咁樣 emoji（surrogate pair）會出 \ud83d\ude80，同 Python ensure_ascii 一致。
function jcsEscape(s: string): string {
  let out = '';
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    const ch = s[i];
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch === '\b') out += '\\b';
    else if (ch === '\f') out += '\\f';
    else if (code < 0x20) out += '\\u' + code.toString(16).padStart(4, '0');
    else out += ch; // RFC 8785 §3.2.2.2：非控制字符（含非 ASCII）原樣 UTF-8 輸出，唔 escape
  }
  return out;
}

// ── canonicalJson：RFC 8785 JCS ────────────────────────────────────
export function canonicalJson(obj: unknown): string {
  if (obj === null) return 'null';
  if (typeof obj === 'boolean') return obj ? 'true' : 'false';
  if (typeof obj === 'number') return String(obj);
  if (typeof obj === 'bigint') return String(obj);
  if (typeof obj === 'string') return '"' + jcsEscape(obj) + '"';
  if (Array.isArray(obj)) return '[' + obj.map((x) => canonicalJson(x)).join(',') + ']';
  if (typeof obj === 'object') {
    // Object.keys().sort() 預設就係 UTF-16 code unit 排序
    const keys = Object.keys(obj as Record<string, unknown>).sort();
    return '{' + keys.map((k) =>
      '"' + jcsEscape(k) + '":' + canonicalJson((obj as Record<string, unknown>)[k])
    ).join(',') + '}';
  }
  throw new Error('canonicalJson: unsupported type ' + typeof obj);
}

// ── digest 工具 ─────────────────────────────────────────────────────
export function digestBytes(data: Buffer | Uint8Array): string {
  return 'sha256:' + createHash('sha256').update(data).digest('hex');
}

export function contentDigest(path: string): string {
  return digestBytes(readFileSync(path));
}

export function canonicalDigest(obj: unknown): string {
  return digestBytes(Buffer.from(canonicalJson(obj), 'utf8'));
}

export function canonicalDigestFile(path: string): string {
  const raw = readFileSync(path);
  try {
    const obj = JSON.parse(raw.toString('utf8'));
    if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
      throw new Error('not a JSON object');
    }
    return canonicalDigest(obj);
  } catch {
    return digestBytes(raw); // 非 JSON object → fall back contentDigest
  }
}

// ── writeReceipt ──────────────────────────────────────────────────
export interface OutputMeta {
  content_digest: string;
  canonical_digest: string;
  status: string;
}

export interface Receipt {
  protocol: string;
  version: string;
  task_id: string;
  from: { agent_id: string; vendor: string };
  to: { agent_id: string; vendor: string };
  epoch: number;
  typed_reason: string;
  note: string;
  outputs: Record<string, OutputMeta>;
}

const SAFE_NAME_RE = /^[^/\\\x00]+$/;

function safeName(name: unknown): name is string {
  if (typeof name !== 'string' || name.length === 0) return false;
  if (name !== name.trim() || name.includes('\x00')) return false;
  if (name === '.' || name === '..' || name.includes('..')) return false;
  if (!SAFE_NAME_RE.test(name)) return false;
  return true;
}

const SAFE_TASK_ID_RE = /^[A-Za-z0-9_-]{1,128}$/;

export function writeReceipt(
  taskId: string,
  fromAgent: string,
  toAgent: string,
  prevOutputs: Array<string | { path: string; status?: string }>,
  newOutputs: Array<string | { path: string; status?: string }>,
  opts: { fromVendor?: string; toVendor?: string; typedReason?: string; note?: string } = {},
): Receipt {
  if (!SAFE_TASK_ID_RE.test(taskId)) {
    throw new Error('invalid task_id: ' + JSON.stringify(taskId));
  }
  const outputs: Record<string, OutputMeta> = {};
  let finalReason = opts.typedReason ?? PASS;

  for (const src of [prevOutputs, newOutputs]) {
    for (const item of src) {
      const pathStr = typeof item === 'string' ? item : (item.path || '');
      if (!pathStr) continue; // 空 path 略過
      if (!safeName(pathStr)) {
        finalReason = REJECT; // 唔安全 path fail-closed
        continue;
      }
      const p = join(receiptsDir, pathStr);
      if (!existsSync(p)) {
        finalReason = REJECT;
        outputs[pathStr] = { content_digest: digestBytes(Buffer.alloc(0)), canonical_digest: digestBytes(Buffer.alloc(0)), status: REJECT };
        continue;
      }
      const raw = readFileSync(p);
      if (raw.length === 0) {
        finalReason = REJECT; // 空輸出 = silent failure
        outputs[pathStr] = { content_digest: digestBytes(Buffer.alloc(0)), canonical_digest: digestBytes(Buffer.alloc(0)), status: REJECT };
        continue;
      }
      outputs[pathStr] = {
        content_digest: contentDigest(p),
        canonical_digest: canonicalDigestFile(p),
        status: PASS,
      };
    }
  }

  const receipt: Receipt = {
    protocol: 'rbp',
    version: '0.1',
    task_id: taskId,
    from: { agent_id: fromAgent, vendor: opts.fromVendor || fromAgent },
    to: { agent_id: toAgent, vendor: opts.toVendor || toAgent },
    epoch: Math.floor(Date.now() / 1000),
    typed_reason: finalReason,
    note: opts.note ?? '',
    outputs,
  };
  const outPath = join(receiptsDir, taskId + '.json');
  const tmpPath = outPath + '.tmp';
  const fd = openSync(tmpPath, 'w');
  writeFileSync(fd, canonicalJson(receipt), 'utf8');
  fsyncSync(fd);
  closeSync(fd);
  renameSync(tmpPath, outPath);
  return receipt;
}

// ── densityCheck ──────────────────────────────────────────────────
export function densityCheck(receipt: Record<string, unknown>): [boolean, number] {
  let present = 0;
  for (const f of REQUIRED_FIELDS) {
    if (f in receipt && receipt[f] !== null && receipt[f] !== undefined) present++;
  }
  const metric = present / REQUIRED_FIELDS.length;
  if (metric < MIN_DENSITY) return [false, metric];
  const outputs = receipt.outputs;
  if (typeof outputs !== 'object' || outputs === null || Array.isArray(outputs) || Object.keys(outputs).length === 0) {
    return [false, 0];
  }
  return [true, metric];
}

// ── verifyReceipt ─────────────────────────────────────────────────
export function verifyReceipt(taskId: string, expectFrom: string, maxAge = 3600): [boolean, string] {
  const path = join(receiptsDir, taskId + '.json');
  if (!existsSync(path)) return [false, 'receipt file not found: ' + path];

  let receipt: unknown;
  try {
    receipt = JSON.parse(readFileSync(path, 'utf8'));
  } catch (e) {
    return [false, 'failed to read receipt: ' + String(e)];
  }
  if (receipt === null || typeof receipt !== 'object' || Array.isArray(receipt)) {
    return [false, 'receipt is not a JSON object'];
  }
  const r = receipt as Record<string, unknown>;

  // ① density
  const [dOk, density] = densityCheck(r);
  if (!dOk) return [false, 'INCOMPLETE: density ' + density.toFixed(2) + ' < ' + MIN_DENSITY];

  // ② scope
  const sender = r.from as Record<string, unknown> | undefined;
  if (typeof sender !== 'object' || sender === null || sender.agent_id !== expectFrom) {
    return [false, 'scope mismatch: receipt.from=' + JSON.stringify(sender) + ', expected=' + expectFrom];
  }

  // ③ digest
  const outputs = r.outputs as Record<string, OutputMeta> | undefined;
  if (typeof outputs !== 'object' || outputs === null) return [false, 'outputs is not a map'];
  for (const [name, meta] of Object.entries(outputs)) {
    if (!safeName(name)) return [false, 'unsafe output name: ' + JSON.stringify(name)];
    if (typeof meta !== 'object' || meta === null) return [false, 'output metadata not a map for ' + JSON.stringify(name)];
    const p = join(receiptsDir, name);
    if (!existsSync(p)) return [false, 'output file missing: ' + name];
    try {
      if (contentDigest(p) !== meta.content_digest) return [false, 'content_digest mismatch for ' + name];
      if (canonicalDigestFile(p) !== meta.canonical_digest) return [false, 'canonical_digest mismatch for ' + name];
    } catch (e) {
      return [false, 'digest failed for ' + name + ': ' + String(e)];
    }
  }

  // ④ epoch：本地時鐘，防舊 state 同未來時間
  // STALE-EPOCH 拆兩子例（結構性 vs 時效性，同 Pikature 收斂 2026-09）：
  //   結構性（EPOCH-STRUCTURAL）= epoch 本身無效（type 錯／未來時間），issuer 錯，換 receipt 先得，重試無用。
  //   時效性（EPOCH-STALE）= epoch 有效但過期（age > maxAge），freshness 問題，可要求重新簽發。
  const epoch = r.epoch as number;
  if (typeof epoch !== 'number' || !Number.isInteger(epoch)) {
    return [false, 'EPOCH-STRUCTURAL: invalid epoch type ' + typeof epoch];
  }
  const age = Math.floor(Date.now() / 1000) - epoch;
  if (age < 0) return [false, 'EPOCH-STRUCTURAL: future epoch age=' + age + 's (issuer clock skew / forged timestamp)'];
  if (age > maxAge) return [false, 'EPOCH-STALE: age=' + age + 's > max_age=' + maxAge + 's (freshness)'];

  // ⑤ verdict
  if (r.typed_reason !== PASS) return [false, 'verdict not PASS: ' + String(r.typed_reason)];

  return [true, 'OK'];
}

// ── 見證層驗證（§12 見證與時效 · v0.3 前置）────────────────────────
// 「誰」母題四條，逐條可證偽（能被負控測出來的才叫約束）

export function checkIndependent(issuerId: unknown, beneficiaryId: unknown): [boolean, string] {
  if (issuerId == null || beneficiaryId == null) {
    return [false, 'MISSING-IDENTITY: issuer/beneficiary 缺一，無法判定獨立性'];
  }
  if (issuerId === beneficiaryId) {
    return [false, 'SELF-SIGNED: issuer=' + String(issuerId) + ' == beneficiary（自簽 ≠ 獨立見證）'];
  }
  return [true, 'OK'];
}

export function checkExpiry(expiresAt: unknown, now: number, fieldName = 'expiry'): [boolean, string] {
  if (expiresAt == null) {
    return [false, 'NO-EXPIRY: ' + fieldName + ' 缺到期日（冇到期日 = 靜默失效）'];
  }
  if (typeof expiresAt === 'number' && expiresAt <= now) {
    return [false, 'EXPIRED: ' + fieldName + ' expires_at=' + expiresAt + ' <= now=' + now];
  }
  return [true, 'OK'];
}

export function checkZeroEmitted(value: unknown, fieldName: string): [boolean, string] {
  if (value === null || value === undefined) {
    return [false, 'FAKE-ZERO: ' + fieldName + ' 缺計數（冇數過 ≠ 冇發生）'];
  }
  return [true, 'OK'];
}

export function checkClosedEnum(value: unknown, allowedSet: Set<unknown>, fieldName: string): [boolean, string] {
  if (!allowedSet.has(value)) {
    return [false, 'ENUM-DRIFT: ' + fieldName + '=' + String(value) + ' 超出閉集（超出即 UNKNOWN）'];
  }
  return [true, 'OK'];
}

export function verifyWitnessBlock(w: Record<string, unknown>, now: number, beneficiary: string): [boolean, string] {
  const cs = w.countersign as Record<string, unknown> | undefined;
  if (cs != null) {
    let r = checkIndependent(cs.issuer, beneficiary);
    if (!r[0]) return [false, 'countersign: ' + r[1]];
    r = checkExpiry(cs.expires_at, now, 'countersign.expires_at');
    if (!r[0]) return [false, 'countersign: ' + r[1]];
  }
  const rt = w.retention as Record<string, unknown> | undefined;
  if (rt != null) {
    let r = checkIndependent(rt.retained_by, beneficiary);
    if (!r[0]) return [false, 'retention: ' + r[1]];
    r = checkExpiry(rt.retained_until, now, 'retention.retained_until');
    if (!r[0]) return [false, 'retention: ' + r[1]];
  }
  const counters = (w.counters || {}) as Record<string, unknown>;
  for (const f of ['check_ran_n', 'observer_count_n']) {
    if (f in counters) {
      const r = checkZeroEmitted(counters[f], f);
      if (!r[0]) return [false, r[1]];
    }
  }
  const tr = w.typed_reason;
  if (tr != null) {
    const r = checkClosedEnum(tr, new Set([PASS, REJECT, UNKNOWN, QUARANTINE]), 'typed_reason');
    if (!r[0]) return [false, r[1]];
  }
  return [true, 'OK'];
}
