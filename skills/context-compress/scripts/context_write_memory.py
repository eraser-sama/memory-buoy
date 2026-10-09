#!/usr/bin/env python3
"""写入上下文记忆文件：front matter 由脚本生成，模型只准备正文。"""
from __future__ import annotations

import argparse
import os
import random
import re
import string
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

# 让脚本在任意 cwd 下都能找到同目录的 context_mem 模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from context_mem import memory_base


TZ_OFFSET = int(os.environ.get("CONTEXT_TZ_OFFSET", "0"))


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=TZ_OFFSET))).isoformat(timespec="seconds")


def _rand6() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _choose_path(project_root: Path, session_id: str) -> Path:
    base = memory_base(str(project_root))
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
    except OSError as exc:
        print(f"context_write_memory: backup failed: {exc}", file=sys.stderr)
    _rotate_backups(target.parent, session_id)


def _update_latest(base: Path, target: Path, saved_at: str, session_id: str) -> None:
    latest = base / "latest.md"
    # 记忆目录可能在项目根外（CONTEXT_MEMORY_DIR 场景），统一写绝对路径，
    # 避免 relative_to 依赖"记忆目录在项目根下"。
    rel = str(target.resolve())
    content = (
        "---\n"
        f"path: {rel}\n"
        f"saved_at: {saved_at}\n"
        f"saved_by: {session_id}\n"
        "---\n"
    )
    tmp = latest.with_name(latest.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, latest)
    except OSError as exc:
        print(f"context_write_memory: latest.md update failed: {exc}", file=sys.stderr)


def _validate_next_action(body: str):
    """结构校验"下一步"章节：存在 + 非空 + 无占位符。返回 (消息, 是否通过)。

    占位符命中：TBD、待定、待补充、placeholder、TODO（大小写不敏感）。
    字数不硬卡，但要求有实质内容（≥5 字符且非纯标点/空白）。
    """
    section = re.search(r"^##\s+下一步\s*$", body, re.MULTILINE)
    if not section:
        return "body missing '## 下一步' section", False

    tail = body[section.end():]
    next_line = tail.lstrip("\n")
    # 去掉下一个二级标题之前的部分
    next_end = re.search(r"^##\s+", next_line, re.MULTILINE)
    if next_end:
        next_line = next_line[:next_end.start()]
    next_line = next_line.strip()

    if not next_line:
        return "'## 下一步' section is empty", False
    if len(next_line.strip()) < 5:
        return f"'## 下一步' too short: {next_line!r}", False

    placeholder = re.search(
        r"\b(TBD|待定|待补充|placeholder|TODO)\b", next_line, re.IGNORECASE
    )
    if placeholder:
        return f"'## 下一步' contains placeholder: {placeholder.group(0)}", False
    return "", True


def _verify_written(path: Path) -> bool:
    """写后自校验：读回文件，确认 front matter 关键字段与正文存在。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"post-write read failed: {exc}", file=sys.stderr)
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    fm_block = text[3:end]
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        return False
    required = ("schema", "project", "status", "saved_at", "saved_by", "resumed_at")
    if not all(k in fm for k in required):
        return False
    if not fm.get("status"):
        return False
    body = text[end + 5:].strip()
    if not body:
        return False
    return True


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

    try:
        body = body_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read body file: {exc}", file=sys.stderr)
        return 1

    # ---------- "下一步"质量校验（结构校验，不按字数卡）----------
    next_action, ok = _validate_next_action(body)
    if not ok:
        print(f"next-step validation failed: {next_action}", file=sys.stderr)
        return 1

    try:
        target = _choose_path(project_root, args.session_id)
    except OSError as exc:
        print(f"cannot create memory dir: {exc}", file=sys.stderr)
        return 1

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

    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        print(f"cannot write memory file: {exc}", file=sys.stderr)
        return 1

    # ---------- 写后自校验：读回验证 front matter 与正文非空 ----------
    if not _verify_written(target):
        print(f"post-write verification failed: {target}", file=sys.stderr)
        return 1

    _update_latest(target.parent, target, saved_at, args.session_id)

    print(f"memory written: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())