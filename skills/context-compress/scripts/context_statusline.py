#!/usr/bin/env python3
"""Claude Code statusLine：显示上下文占用 + 写缓存供 Hook 读取。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "memory-buoy"
THROTTLE_SECONDS = 3

YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
RED = "\033[31m"
RESET = "\033[0m"


def _write_cache(session_id: str, payload: dict) -> None:
    """写缓存给 Hook 用。任何失败静默——状态栏不能崩。"""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{session_id}.json"
        if cache_file.is_file():
            try:
                old = json.loads(cache_file.read_text(encoding="utf-8"))
                if (old.get("used_percentage") == payload.get("used_percentage")
                        and time.time() - old.get("written_at_ts", 0) < THROTTLE_SECONDS):
                    return
            except (OSError, json.JSONDecodeError):
                pass
        tmp = cache_file.with_name(cache_file.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache_file)
    except Exception:
        pass


def main() -> None:
    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        print("📊 Context: N/A")
        return

    cw = d.get("context_window") or {}
    pct = cw.get("used_percentage")
    size = cw.get("context_window_size") or 200000
    cu = cw.get("current_usage") or {}
    session_id = d.get("session_id") or ""
    ws = d.get("workspace") or {}
    project_dir = ws.get("project_dir") or d.get("cwd") or ""
    transcript_path = d.get("transcript_path") or ""
    model_id = (d.get("model") or {}).get("id") or ""

    if session_id:
        _write_cache(session_id, {
            "used_percentage": pct,
            "context_window_size": size,
            "current_usage": cu,
            "project_dir": project_dir,
            "session_id": session_id,
            "transcript_path": transcript_path,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "written_at_ts": int(time.time()),
        })

    if pct is None:
        print("📊 Context: N/A")
        return

    used = int(pct)
    if used < 60:
        color, warn = YELLOW, ""
    elif used < 80:
        color, warn = ORANGE, ""
    else:
        color, warn = RED, " ⚠️ 上下文即将溢出"

    total_in = cw.get("total_input_tokens") or 0
    tokens_k = total_in // 1000
    size_k = size // 1000

    uncertain = ""
    if not model_id.startswith("claude-") and size == 200000:
        uncertain = " ?"
    print(f"{color}📊 Context: {used}% (~{tokens_k}k/{size_k}k){warn}{uncertain}{RESET}")


if __name__ == "__main__":
    main()