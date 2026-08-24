#!/usr/bin/env python3
"""
5-agent team pipeline: chain five local agents from different vendors.

    Maco   (OpenClaw, local install, agnes-2.0-flash)  -> writes fibonacci.py
    Kim    (OpenClaw, kimi instance, kimi-coding)      -> writes test_fibonacci.py
    Claude (Claude Code)                               -> code review  (claude_review.md)
    Codex  (OpenAI Codex CLI)                          -> security/perf review (codex_review.md)
    Sheila (Hermes)                                    -> writes README.md

Each agent only *replies* with content (no shell execution requested from
them), so the wrapper needs no exec approvals from any of them. The wrapper
saves every raw response, extracts the deliverable, and finally verifies the
collaboration by actually running the tests.

Exit code 0 on full success, 1 if any stage failed.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "output"
PROMPTS = BASE / "prompts"
OUT.mkdir(exist_ok=True)
PROMPTS.mkdir(exist_ok=True)
RECEIPTS = OUT / "receipts"
RECEIPTS.mkdir(exist_ok=True)

HOME = os.path.expanduser("~")
OPENCLAW = os.path.expanduser("~/.npm-global/bin/openclaw")
HERMES = os.path.expanduser("~/.local/bin/hermes")
CLAUDE = "/usr/local/bin/claude"
CODEX = os.path.expanduser("~/.local/bin/codex")

FAILED = []

WORKSPACE = BASE.parent
AGENTS_MD_PATH = WORKSPACE / "AGENTS.md"


def shared_context():
    """團隊共享記憶（AGENTS.md）——每次 call agent 前硬塞入 prompt，保證成隊同 context。"""
    try:
        content = AGENTS_MD_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""
    return (
        "\n\n【團隊共享記憶 AGENTS.md — 開工前必讀】\n"
        f"{content}\n"
        "【共享記憶完】\n\n"
    )


def run(cmd, env=None, timeout=300, cwd=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=timeout, cwd=cwd)
        return p
    except subprocess.TimeoutExpired:
        print(f"   ✗ 超時（>{timeout}s）：{' '.join(str(c) for c in cmd[:4])}…")
        return None
    except FileNotFoundError as e:
        print(f"   ✗ 搵唔到命令：{e}")
        return None


def extract_openclaw(raw):
    """Pull the final assistant text out of `openclaw agent --json` output."""
    try:
        d = json.loads(raw)
    except Exception:
        return raw.strip()
    meta = d.get("meta") if isinstance(d, dict) else None
    if isinstance(meta, dict):
        t = meta.get("finalAssistantVisibleText") or meta.get("finalAssistantRawText")
        if t:
            return t.strip()
    t = d.get("finalAssistantVisibleText") or d.get("finalAssistantRawText")
    return (t or raw).strip()


def extract_codex(raw):
    """Clean `codex exec` stdout: drop the leading 'codex' banner and the
    trailing 'tokens used' accounting block."""
    lines = raw.splitlines()
    if lines and lines[0].strip() == "codex":
        lines = lines[1:]
    for i, ln in enumerate(lines):
        if ln.strip() == "tokens used":
            lines = lines[:i]
            break
    text = "\n".join(lines).strip()
    return text or raw.strip()


def strip_fences(t):
    """Remove a surrounding ```lang ... ``` fence if present."""
    m = re.search(r"```(?:python|bash|sh|shell|markdown|md)?\s*\n(.*?)```", t, re.S)
    return m.group(1).strip() if m else t.strip()


def trim_review(t):
    """Trim trailing decorative rules (---- / ====) some CLIs append."""
    lines = t.splitlines()
    while lines and re.fullmatch(r"[-=─]{3,}", lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).strip()


def write(name, text):
    (OUT / name).write_text(text)
    return text


# ── Receipt-bearing 交接 ──────────────────────────────────────────
# 每個 agent 完成後寫 receipt（epoch + digest + typed_reason），
# 下游開工前先 verify（digest 對 + epoch 未過期 + typed_reason == PASS）。

def file_digest(name):
    """對 output file 做 sha256。"""
    h = hashlib.sha256()
    h.update((OUT / name).read_bytes())
    return "sha256:" + h.hexdigest()


def write_receipt(task_id, from_agent, to_agent, prev_outputs, new_outputs,
                  typed_reason="PASS", note=""):
    """寫一張交接 receipt，累積 upstream 嘅 outputs。"""
    outputs = dict(prev_outputs)
    for name in new_outputs:
        outputs[name] = file_digest(name)
    receipt = {
        "task_id": task_id,
        "from": from_agent,
        "to": to_agent,
        "epoch": int(time.time()),
        "typed_reason": typed_reason,
        "outputs": outputs,
        "note": note,
    }
    (RECEIPTS / f"{task_id}.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2))
    print(f"   ↳ receipt: {task_id} {from_agent}→{to_agent} [{typed_reason}] "
          f"{len(outputs)} 個 file")
    return outputs


def verify_receipt(task_id, expect_from, max_age=3600):
    """下游開工前驗 receipt。返 (ok, msg)。"""
    path = RECEIPTS / f"{task_id}.json"
    if not path.exists():
        return False, f"receipt 唔存在：{task_id}"
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"receipt 讀唔到：{e}"
    if r.get("from") != expect_from:
        return False, f"來源唔啱：期望 {expect_from}，實際 {r.get('from')}"
    if r.get("typed_reason") != "PASS":
        return False, f"typed_reason={r.get('typed_reason')}（唔係 PASS，fail-closed）"
    age = int(time.time()) - int(r.get("epoch", 0))
    if age > max_age:
        return False, f"receipt 過期：{age}s > {max_age}s"
    for name, digest in r.get("outputs", {}).items():
        if not (OUT / name).exists():
            return False, f"output 唔見咗：{name}"
        if file_digest(name) != digest:
            return False, f"digest 唔對：{name}"
    return True, "OK"


def step_maco():
    print("── [1/5] Maco（OpenClaw 本地 / agnes）→ fibonacci.py")
    prompt = shared_context() + (
        "你係 Maco，一個 coding agent。任務：寫一個 Python 模組，檔案名叫 fibonacci.py。\n\n"
        "要求：\n"
        "- 提供函數 fib(n)，回傳 Fibonacci 數列第 n 項（n 由 0 開始，fib(0)=0, fib(1)=1）\n"
        "- 提供 main 區塊，支援 `python fibonacci.py <n>` 印出第 n 項\n"
        "- 直接喺回覆輸出完整 Python 程式碼，包喺 ```python ``` 程式碼塊入面\n"
        "- 唔好執行任何命令，唔好加額外解釋"
    )
    (PROMPTS / "1_maco.txt").write_text(prompt)
    p = run([OPENCLAW, "agent", "--local", "--agent", "main",
             "--message-file", str(PROMPTS / "1_maco.txt"),
             "--json", "--timeout", "300"])
    if p is None:
        FAILED.append("Maco")
        return None
    write("maco.raw.json", p.stdout)
    write("maco.err.log", p.stderr)
    code = strip_fences(extract_openclaw(p.stdout))
    write("fibonacci.py", code)
    print(f"   ✓ fibonacci.py（{len(code.splitlines())} 行）")
    return write_receipt("fib-001", "Maco", "Kim", {}, ["fibonacci.py"])


def step_kim(prev_outputs):
    print("── [2/5] Kim（OpenClaw kimi instance / kimi-coding）→ test_fibonacci.py")
    ok, msg = verify_receipt("fib-001", "Maco")
    if not ok:
        print(f"   ✗ 驗 receipt 失敗（fail-closed）：{msg}")
        FAILED.append("Kim")
        return None
    fib = (OUT / "fibonacci.py").read_text()
    prompt = shared_context() + (
        "你係 Kim，一個 QA / coding agent。任務：為以下 fibonacci.py 寫 pytest 測試檔，"
        "檔案名叫 test_fibonacci.py。\n\n"
        f"fibonacci.py 內容：\n```python\n{fib}\n```\n\n"
        "要求：\n"
        "- 覆蓋正常情況（fib(0)=0, fib(1)=1, fib(10)=55）同 edge case（負數、非整數）\n"
        "- 直接喺回覆輸出完整 Python 程式碼，包喺 ```python ``` 程式碼塊入面\n"
        "- 唔好執行任何命令，唔好加額外解釋"
    )
    (PROMPTS / "2_kim.txt").write_text(prompt)
    env = {
        "OPENCLAW_CONFIG_PATH": f"{HOME}/.kimi_openclaw/openclaw.json",
        "OPENCLAW_STATE_DIR": f"{HOME}/.kimi_openclaw/state",
    }
    p = run([OPENCLAW, "agent", "--local", "--agent", "main",
             "--message-file", str(PROMPTS / "2_kim.txt"),
             "--json", "--timeout", "300"], env=env)
    if p is None:
        FAILED.append("Kim")
        return None
    write("kim.raw.json", p.stdout)
    write("kim.err.log", p.stderr)
    code = strip_fences(extract_openclaw(p.stdout))
    write("test_fibonacci.py", code)
    print(f"   ✓ test_fibonacci.py（{len(code.splitlines())} 行）")
    return write_receipt("fib-002", "Kim", "Claude", prev_outputs, ["test_fibonacci.py"])


def step_claude(prev_outputs):
    print("── [3/5] Claude（Claude Code）→ code review（claude_review.md）")
    ok, msg = verify_receipt("fib-002", "Kim")
    if not ok:
        print(f"   ✗ 驗 receipt 失敗（fail-closed）：{msg}")
        FAILED.append("Claude")
        return None
    prompt = shared_context() + (
        "你係 Claude，做 code review。請 review 以下兩個檔案：\n"
        f"- {OUT / 'fibonacci.py'}\n"
        f"- {OUT / 'test_fibonacci.py'}\n\n"
        "輸出一個 markdown review，包含：整體評價、發現嘅問題（bugs、edge cases、風格）、"
        "具體改善建議。直接輸出 markdown 內容，唔好修改任何檔案。"
    )
    p = run([CLAUDE, "-p", prompt, "--output-format", "text"], timeout=400, cwd=str(OUT))
    if p is None:
        FAILED.append("Claude")
        return None
    write("claude.raw.txt", p.stdout)
    write("claude.err.log", p.stderr)
    review = trim_review(p.stdout.strip())
    write("claude_review.md", review)
    print(f"   ✓ claude_review.md（{len(review.splitlines())} 行）")
    return write_receipt("fib-003", "Claude", "Codex", prev_outputs, ["claude_review.md"])


def step_codex(prev_outputs):
    print("── [4/5] Codex（OpenAI Codex CLI）→ security/perf review（codex_review.md）")
    ok, msg = verify_receipt("fib-003", "Claude")
    if not ok:
        print(f"   ✗ 驗 receipt 失敗（fail-closed）：{msg}")
        FAILED.append("Codex")
        return None
    prompt = shared_context() + (
        "你係 Codex，做 security 同 performance review。請 review 以下兩個檔案：\n"
        f"- {OUT / 'fibonacci.py'}\n"
        f"- {OUT / 'test_fibonacci.py'}\n\n"
        "輸出一個 markdown review，重點：安全性問題、效能問題、輸入處理、測試覆蓋漏洞。"
        "直接輸出 markdown 內容，唔好修改任何檔案。"
    )
    p = run([CODEX, "exec", "--skip-git-repo-check", "--cd", str(OUT),
             "-s", "read-only", prompt], timeout=600)
    if p is None:
        FAILED.append("Codex")
        return None
    write("codex.raw.txt", p.stdout)
    write("codex.err.log", p.stderr)
    review = trim_review(extract_codex(p.stdout))
    write("codex_review.md", review)
    print(f"   ✓ codex_review.md（{len(review.splitlines())} 行）")
    return write_receipt("fib-004", "Codex", "Sheila", prev_outputs, ["codex_review.md"])


def step_sheila(prev_outputs):
    print("── [5/5] Sheila（Hermes）→ README.md")
    ok, msg = verify_receipt("fib-004", "Codex")
    if not ok:
        print(f"   ✗ 驗 receipt 失敗（fail-closed）：{msg}")
        FAILED.append("Sheila")
        return None
    stale = BASE.parent / "README.md"
    if stale.exists():
        stale.unlink()
    fib = (OUT / "fibonacci.py").read_text()
    tests = (OUT / "test_fibonacci.py").read_text()
    prompt = shared_context() + (
        "你係 Sheila，一個文檔 agent。任務：為以下 Python 專案寫 README.md，直接以 markdown 回覆。\n\n"
        f"fibonacci.py 內容：\n```python\n{fib}\n```\n\n"
        f"test_fibonacci.py 內容：\n```python\n{tests}\n```\n\n"
        "要求：\n"
        "- README 要包含：專案簡介、安裝方法、使用方式（含 CLI 例子）、測試方法\n"
        "- 直接喺回覆輸出 README.md 嘅完整 markdown 內容，唔好加額外解釋，唔好執行任何命令"
    )
    (PROMPTS / "3_sheila.txt").write_text(prompt)
    p = run([HERMES, "-z", prompt], timeout=300)
    if p is None:
        FAILED.append("Sheila")
        return None
    write("sheila.raw.txt", p.stdout)
    write("sheila.err.log", p.stderr)
    md = extract_markdown(p.stdout)
    print(f"   ✓ README.md（{len(md.splitlines())} 行）")
    return write_receipt("fib-005", "Sheila", "DONE", prev_outputs, ["README.md"])


def extract_markdown(raw):
    """Extract the README body from a Hermes reply (Hermes may write the file
    itself, or just reply; handle both)."""
    candidate = BASE.parent / "README.md"
    if candidate.is_file():
        text = candidate.read_text()
        if text.strip().startswith("#"):
            write("README.md", text.strip())
            return text.strip()
    m = re.search(r"^#\s+.+$", raw, re.M)
    if m:
        body = "\n".join(ln for ln in raw[m.start():].splitlines() if ln.strip())
        write("README.md", body)
        return body
    write("README.md", raw.strip())
    return raw.strip()


def verify():
    print("── 驗證：五個 agent 嘅合作成果可唔可以跑得郁")
    sys.path.insert(0, str(OUT))
    ok = True
    try:
        import fibonacci
        seq = [fibonacci.fib(i) for i in range(10)]
        assert seq == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34], f"fib() 結果唔啱：{seq}"
        print(f"   ✓ fib() 頭 10 項正確：{seq}")
    except Exception as e:
        ok = False
        print(f"   ✗ fibonacci.py 有問題：{e}")

    p = run([sys.executable, "-m", "pytest", str(OUT / "test_fibonacci.py"), "-q", "--tb=short"],
            timeout=120)
    if p is None:
        ok = False
    elif p.returncode == 0:
        print("   ✓ Kim 寫嘅 pytest 全部通過")
        tail = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
        if tail:
            print("     " + tail[-1])
    else:
        ok = False
        print("   ✗ pytest 有失敗（見下）")
        print((p.stdout + p.stderr).strip()[:800])
    return ok


def main():
    outputs = step_maco()
    if outputs is not None:
        outputs = step_kim(outputs)
    if outputs is not None:
        outputs = step_claude(outputs)
    if outputs is not None:
        outputs = step_codex(outputs)
    if outputs is not None:
        outputs = step_sheila(outputs)

    passed = not FAILED
    if passed:
        passed = verify()

    print("\n── 成果")
    for f in sorted(OUT.iterdir()):
        if f.is_file():
            print(f"   {f.name}  ({f.stat().st_size} bytes)")

    for name in FAILED:
        print(f"   ✗ {name} 步驟失敗")
    print("\n完成。原始輸出喺 demo_agents/output/*.raw.*，prompt 喺 demo_agents/prompts/。")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
