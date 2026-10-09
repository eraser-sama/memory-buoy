#!/usr/bin/env python3
"""UserPromptSubmit Hook：触发词检测 + 门控粗筛 + 注入强指令。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 让脚本在任意 cwd 下都能找到同目录的 context_mem 模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from context_mem import (
    list_pending_memories,
    read_front_matter,
    normalize_path,
    project_matches,
)

CACHE_DIR = Path.home() / ".cache" / "memory-buoy"
# 主动提醒阈值；0 = 关闭（默认）。环境变量 CONTEXT_PROMPT_AT 可调。
PROMPT_AT = int(os.environ.get("CONTEXT_PROMPT_AT", "") or 0)
# 主动提醒冷却时长（秒），默认 24 小时。
PROMPT_COOLDOWN = int(os.environ.get("CONTEXT_PROMPT_COOLDOWN", "86400"))

TRIGGER_COMPRESS = ("【压缩上下文】", "[COMPRESS]")
TRIGGER_RESUME = ("【继续】", "[RESUME]")


def _read_cache(session_id: str) -> dict:
    """读 statusline 写入的占用率缓存（只读）。损坏或缺失返回空 dict。"""
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


def _is_trigger_prompt(prompt_lower: str) -> bool:
    """当前消息是否含压缩/恢复触发词（用于主动提醒时不打扰触发流程）。"""
    return any(t.lower() in prompt_lower for t in TRIGGER_COMPRESS) or any(
        t.lower() in prompt_lower for t in TRIGGER_RESUME
    )


def _prompt_mark_path(session_id: str) -> Path:
    return CACHE_DIR / f"{session_id}.prompted"


def _should_prompt(session_id: str) -> bool:
    """冷却检查：距上次提醒已超过 COOLDOWN 则返回 True。异常静默放行。"""
    try:
        f = _prompt_mark_path(session_id)
        if not f.is_file():
            return True
        last = json.loads(f.read_text(encoding="utf-8")).get("last_prompted_at", 0)
        return (time.time() - last) >= PROMPT_COOLDOWN
    except Exception:
        return True


def _mark_prompted(session_id: str) -> None:
    """写主动提醒冷却标记到 ~/.cache/memory-buoy/<session_id>.prompted。

    只写临时标记文件，不碰 statusline 缓存，不碰 <project>/.claude/ 下任何文件。
    保持 Hook 只读不改记忆文件的红线。
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _prompt_mark_path(session_id).with_name(
            _prompt_mark_path(session_id).name + ".tmp"
        )
        tmp.write_text(
            json.dumps({"last_prompted_at": int(time.time())}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, _prompt_mark_path(session_id))
    except Exception:
        pass


def _emit(ctx: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def _pending_list_text(memories) -> str:
    """把 pending 清单拼成给模型/用户看的文本，按 saved_at 降序已排序。"""
    lines = []
    for i, (path, fm) in enumerate(memories, start=1):
        saved_at = fm.get("saved_at", "")
        lines.append(f"{i}. {path} (saved_at: {saved_at})")
    return "\n".join(lines)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("")
        return

    prompt = payload.get("prompt", "")
    prompt_lower = prompt.lower()
    session_id = payload.get("session_id", "")
    cache = _read_cache(session_id)

    # ---------- 主动提醒（无触发词时才可能触发）----------
    if PROMPT_AT and not _is_trigger_prompt(prompt_lower) and session_id:
        pct = cache.get("used_percentage")
        if isinstance(pct, (int, float)) and pct >= PROMPT_AT and _should_prompt(session_id):
            _mark_prompted(session_id)
            _emit(f"占用率已达 {pct}%，建议考虑【压缩上下文】以保持会话健康。"
                  "如无需要可忽略此提醒。")
            return

    # ---------- 【压缩上下文】----------
    if any(t.lower() in prompt_lower for t in TRIGGER_COMPRESS):
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
    if any(t.lower() in prompt_lower for t in TRIGGER_RESUME):
        project_root = _project_root(payload, cache)
        pending = list_pending_memories(project_root)

        if not pending:
            _emit("【继续】触发。未找到当前项目的记忆文件，将按普通继续处理。")
            return

        # 只有一个 pending：保持原行为，直接注入。
        if len(pending) == 1:
            memory, fm = pending[0]
            _emit(f"【继续】触发，门控通过。请读取记忆文件 {memory}，按【下一步】继续执行。"
                  "执行成功后必须调用 context_update_status.py 把 status 更新为 consumed。")
            return

        # ≥2 个 pending：列出清单，让模型展示给用户挑选。
        _emit(f"【继续】触发。当前项目有 {len(pending)} 个待恢复记忆（按保存时间从新到旧）：\n"
              f"{_pending_list_text(pending)}\n"
              "请把这份清单展示给用户，让用户指定恢复哪一个；用户确认后读取对应记忆文件，"
              "按【下一步】继续执行，成功后调用 context_update_status.py 把 status 更新为 consumed。")
        return

    # 无触发词
    print("{}")


if __name__ == "__main__":
    main()