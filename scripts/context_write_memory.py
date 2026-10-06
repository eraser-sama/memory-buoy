#!/usr/bin/env python3
"""写入上下文记忆文件：front matter 由脚本生成，模型只准备正文。"""
from __future__ import annotations

import argparse
import os
import random
import string
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml


TZ_OFFSET = int(os.environ.get("CONTEXT_TZ_OFFSET", "0"))


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=TZ_OFFSET))).isoformat(timespec="seconds")


def _rand6() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _choose_path(project_root: Path, session_id: str) -> Path:
    base = project_root / ".claude" / "context-memory"
    base.mkdir(parents=True, exist_ok=True)
    if session_id and len(session_id) >= 8 and all(c.isalnum() or c == "-" for c in session_id):
        return base / f"{session_id}.md"
    ts = time.strftime("%Y%m%d_%H%M%S")
    return base / f"{ts}_{_rand6()}.md"


def _rotate_backups(base: Path, session_id: str) -> None:
    prefix = f"CONTEXT_MEMORY_{session_id}_"
    if not session_id:
        prefix = "CONTEXT_MEMORY_"
    baks = sorted(
        [p for p in base.glob("*.md.bak") if p.name.startswith(prefix)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in baks[3:]:
        try:
            old.unlink()
        except OSError:
            pass


def _backup_existing(target: Path, session_id: str) -> None:
    if not target.is_file():
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = target.with_name(f"CONTEXT_MEMORY_{session_id}_{ts}.md.bak")
    try:
        bak.write_bytes(target.read_bytes())
    except OSError:
        pass
    _rotate_backups(target.parent, session_id)


def _update_latest(base: Path, target: Path, saved_at: str, session_id: str) -> None:
    latest = base / "latest.md"
    try:
        rel = target.relative_to(base.parent.parent)
    except ValueError:
        rel = target
    content = (
        "---\n"
        f"path: {rel}\n"
        f"saved_at: {saved_at}\n"
        f"saved_by: {session_id}\n"
        "---\n"
    )
    tmp = latest.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, latest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--session-id", default="")
    ap.add_argument("--body", required=True, help="正文文件路径")
    ap.add_argument("--status", default="pending")
    args = ap.parse_args()

    project_root = Path(args.project_root).resolve()
    body_path = Path(args.body)
    if not body_path.is_file():
        print(f"body file not found: {body_path}", file=sys.stderr)
        return 1

    body = body_path.read_text(encoding="utf-8")
    target = _choose_path(project_root, args.session_id)
    saved_at = _now_iso()

    front = {
        "schema": 1,
        "project": str(project_root),
        "status": args.status,
        "saved_at": saved_at,
        "saved_by": args.session_id,
        "resumed_at": "",
    }
    fm_text = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm_text}\n---\n\n{body.lstrip()}"

    _backup_existing(target, args.session_id)
    tmp = target.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)

    _update_latest(target.parent, target, saved_at, args.session_id)

    print(f"memory written: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
