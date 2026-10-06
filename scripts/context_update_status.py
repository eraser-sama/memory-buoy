#!/usr/bin/env python3
"""更新记忆文件 front matter 的 status 和 resumed_at。"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml


TZ_OFFSET = int(os.environ.get("CONTEXT_TZ_OFFSET", "0"))


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=TZ_OFFSET))).isoformat(timespec="seconds")


def _split_front_matter(text: str):
    if not text.startswith("---"):
        return None, None, None
    end = text.find("\n---", 3)
    if end == -1:
        return None, None, None
    fm = text[3:end]
    rest = text[end + 4:]
    return fm, rest, end


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("memory_file")
    ap.add_argument("new_status")
    args = ap.parse_args()

    path = Path(args.memory_file)
    if not path.is_file():
        print(f"memory file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    fm_raw, rest, _ = _split_front_matter(text)
    if fm_raw is None:
        print("front matter not found", file=sys.stderr)
        return 1

    try:
        fm = yaml.safe_load(fm_raw) or {}
    except Exception as exc:
        print(f"yaml parse error: {exc}", file=sys.stderr)
        return 1

    fm["status"] = args.new_status
    if args.new_status == "consumed":
        fm["resumed_at"] = _now_iso()

    fm_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    new_text = f"---\n{fm_text}\n---\n{rest}"

    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)

    print(f"status updated: {args.new_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
