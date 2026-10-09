#!/usr/bin/env python3
"""context-compress 共享模块：记忆目录解析、pending 记忆扫描与 front matter 解析。

供 context_hook.py、context_statusline.py、context_write_memory.py 共用。
扫描类函数只读，不写任何文件。
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


def read_front_matter(path: Path) -> dict:
    """只扫前两个 --- 之间的字段，用正则提取 status/project/saved_at。失败返回。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return
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


def _project_hash(project_root: str) -> str:
    """项目根 → 稳定哈希（前 12 位 hex）。同一项目跨会话/跨机器路径稳定。"""
    return hashlib.sha1(normalize_path(project_root).encode("utf-8")).hexdigest()[:12]


def memory_base(project_root: str) -> Path:
    """记忆目录解析。

    设了 CONTEXT_MEMORY_DIR：所有项目统一存 $CONTEXT_MEMORY_DIR/<project_hash>/，
    每个项目一个子目录，保证项目隔离。
    未设：默认 <项目根>/.claude/context-memory/。
    读写两侧都用本函数，保证路径一致。
    """
    env = os.environ.get("CONTEXT_MEMORY_DIR", "")
    if env:
        return Path(env) / _project_hash(project_root)
    return Path(project_root) / ".claude" / "context-memory"


def _scan_dir(mem_dir: Path, project_root: str) -> list:
    """扫描单个记忆目录（排除 latest.md 与 .bak），返回 pending 记忆。"""
    results: list = []
    if not mem_dir.is_dir():
        return results
    for p in sorted(mem_dir.glob("*.md")):
        if p.name == "latest.md":
            continue
        fm = read_front_matter(p)
        if fm.get("status") == "pending" and project_matches(fm.get("project", ""), project_root):
            results.append((p, fm))
    return results


def list_pending_memories(project_root: str) -> list:
    """返回该项目下所有 pending 记忆 [(Path, front_matter)]，按 saved_at 降序。

    扫描规则：
    - 设了 CONTEXT_MEMORY_DIR：只扫新目录 $DIR/<hash>/。
      仅当新目录为空且旧目录（<项目根>/.claude/context-memory/）有 pending 时，
      临时回退扫旧目录，作为旧版本迁移兜底。
    - 未设 CONTEXT_MEMORY_DIR：只扫默认旧目录，行为不变。
    另兼容旧单文件 <项目根>/.claude/CONTEXT_MEMORY.md。
    只读，失败静默（路径不可读时返回空清单）。
    """
    primary = memory_base(project_root)
    results = _scan_dir(primary, project_root)

    # 未设 CONTEXT_MEMORY_DIR 时 primary 就是默认目录，无需回退逻辑。
    if not os.environ.get("CONTEXT_MEMORY_DIR"):
        # 兼容旧单文件
        single = Path(project_root) / ".claude" / "CONTEXT_MEMORY.md"
        if single.is_file():
            fm = read_front_matter(single)
            if fm.get("status") == "pending" and project_matches(fm.get("project", ""), project_root):
                results.append((single, fm))
        results.sort(key=lambda item: item[1].get("saved_at", ""), reverse=True)
        return results

    # 设了 CONTEXT_MEMORY_DIR：新目录无 pending 时回退旧目录
    if not results:
        legacy = Path(project_root) / ".claude" / "context-memory"
        results = _scan_dir(legacy, project_root)
        # 兼容旧单文件
        single = Path(project_root) / ".claude" / "CONTEXT_MEMORY.md"
        if single.is_file():
            fm = read_front_matter(single)
            if fm.get("status") == "pending" and project_matches(fm.get("project", ""), project_root):
                results.append((single, fm))
        if results:
            # 在清单里标记来源目录（供 hook 提示用户这是旧目录记忆）
            results = [(p, fm) for p, fm in results]
    results.sort(key=lambda item: item[1].get("saved_at", ""), reverse=True)
    return results