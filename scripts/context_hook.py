#!/usr/bin/env python3
"""UserPromptSubmit Hook：触发词检测 + 门控粗筛 + 注入强指令。"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "claude-context-guardian"

TRIGGER_COMPRESS = "【压缩上下文】"
TRIGGER_RESUME = "【继续】"


def _read_cache(session_id: str) -> dict:
    f = CACHE_DIR / f"{session_id}.json"
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except json.JSONDecodeError as exc:
        print(f"context_hook: cache JSON corrupted: {exc}", file=sys.stderr)
        return {}


def _project_root(hook_payload: dict, cache: dict) -> str:
    if cache.get("project_dir"):
        return cache["project_dir"]
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.environ["CLAUDE_PROJECT_DIR"]
    if hook_payload.get("cwd"):
        return hook_payload["cwd"]
    return os.getcwd()


def _read_front_matter(path: Path) -> dict:
    """只扫前两个 --- 之间的字段，用正则提取 status/project/saved_at。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"context_hook: cannot read memory file: {exc}", file=sys.stderr)
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    out = {}
    for key in ("status", "project", "saved_at"):
        m = re.search(rf"^\s*{key}:\s*(.+)$", block, re.MULTILINE)
        if m:
            val = m.group(1).split("#", 1)[0].strip().strip('"').strip("'")
            out[key] = val
    return out


def _normalize_path(p: str) -> str:
    """规范化路径，跨平台比较用。"""
    try:
        return str(Path(p).resolve())
    except (OSError, RuntimeError):
        return p


def _find_memory_file(project_root: str, session_id: str) -> Path | None:
    base = Path(project_root) / ".claude"
    latest = base / "context-memory" / "latest.md"
    if latest.is_file():
        try:
            lines = latest.read_text(encoding="utf-8").splitlines()
            fm_lines: list[str] = []
            dash_count = 0
            for line in lines:
                if line.strip() == "---":
                    dash_count += 1
                    if dash_count == 2:
                        break
                    continue
                if dash_count == 1:
                    fm_lines.append(line)
            for line in fm_lines:
                if line.lower().startswith("path:"):
                    p = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if p:
                        candidate = Path(project_root) / p if not Path(p).is_absolute() else Path(p)
                        if candidate.is_file():
                            return candidate
        except OSError as exc:
            print(f"context_hook: cannot read latest.md: {exc}", file=sys.stderr)
    single = base / "CONTEXT_MEMORY.md"
    if single.is_file():
        return single
    multi = base / "context-memory" / f"{session_id}.md"
    if multi.is_file():
        return multi
    return None


def _emit(ctx: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("{}")
        return

    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "")
    cache = _read_cache(session_id)

    # ---------- 【压缩上下文】----------
    if TRIGGER_COMPRESS in prompt:
        pct = cache.get("used_percentage")
        if not isinstance(pct, (int, float)):
            _emit("【压缩上下文】触发。但占用率未知，请用户手动确认是否压缩。")
            return
        if pct >= 60:
            _emit(f"【压缩上下文】触发。当前占用约 {pct}%，请立即执行 context-compress Skill："
                  "准备正文内容，调用 context_write_memory.py 落盘，然后提示用户执行 /compact 并说【继续】。")
        elif pct >= 30:
            _emit(f"【压缩上下文】触发。当前占用约 {pct}%，请先询问用户是否确认压缩。")
        else:
            _emit(f"【压缩上下文】触发。当前占用约 {pct}%，占用很低，建议拒绝并提示用户无需压缩。")
        return

    # ---------- 【继续】----------
    if TRIGGER_RESUME in prompt:
        project_root = _project_root(payload, cache)
        memory = _find_memory_file(project_root, session_id)

        if memory is None:
            _emit("【继续】触发。未找到当前项目的记忆文件，将按普通继续处理。")
            return

        fm = _read_front_matter(memory)
        if not fm:
            _emit("【继续】触发。记忆文件头解析失败，将按普通继续处理。")
            return

        status = fm.get("status", "")
        if status != "pending":
            _emit(f"【继续】触发。当前记忆状态为 {status or '未知'}，无需恢复，将按普通继续处理。")
            return

        mem_project = fm.get("project", "")
        if mem_project:
            if _normalize_path(mem_project) != _normalize_path(project_root):
                _emit("【继续】触发。当前项目与记忆文件项目不匹配，已跳过恢复，将按普通继续处理。")
                return

        _emit(f"【继续】触发，门控通过。请读取记忆文件 {memory}，按【下一步】继续执行。"
              "执行成功后必须调用 context_update_status.py 把 status 更新为 consumed。")
        return

    # 无触发词
    print("{}")


if __name__ == "__main__":
    main()