#!/usr/bin/env python3
"""context-compress 共享模块：记忆文件扫描与 front matter 解析。

供 context_hook.py 与 context_statusline.py 共用，避免两处各自实现。
所有函数只读，不写任何文件。
"""
from __future__ import annotations

import re
from pathlib import Path


def read_front_matter(path: Path) -> dict:
    """只扫前两个 --- 之间的字段，用正则提取 status/project/saved_at。失败返回 {}。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
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


def normalize_path(p: str) -> str:
    """规范化路径，跨平台比较用。"""
    try:
        return str(Path(p).resolve())
    except (OSError, RuntimeError):
        return p


def project_matches(mem_project: str, project_root: str) -> bool:
    if not mem_project:
        return True
    return normalize_path(mem_project) == normalize_path(project_root)


def list_pending_memories(project_root: str) -> list:
    """返回该项目下所有 pending 记忆 [(Path, front_matter)]，按 saved_at 降序。

    扫描 <project>/.claude/context-memory/*.md（排除 latest.md 与 .bak），
    并兼容旧单文件 <project>/.claude/CONTEXT_MEMORY.md。
    只读，失败静默（路径不可读时返回空清单）。
    """
    base = Path(project_root) / ".claude"
    mem_dir = base / "context-memory"
    results: list = []
    if mem_dir.is_dir():
        for p in sorted(mem_dir.glob("*.md")):
            if p.name == "latest.md":
                continue
            fm = read_front_matter(p)
            if fm.get("status") == "pending" and project_matches(fm.get("project", ""), project_root):
                results.append((p, fm))
    single = base / "CONTEXT_MEMORY.md"
    if single.is_file():
        fm = read_front_matter(single)
        if fm.get("status") == "pending" and project_matches(fm.get("project", ""), project_root):
            results.append((single, fm))
    results.sort(key=lambda item: item[1].get("saved_at", ""), reverse=True)
    return results
