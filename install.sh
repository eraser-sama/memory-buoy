#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SCRIPTS_DIR="${CLAUDE_DIR}/scripts"
SKILL_DIR="${CLAUDE_DIR}/skills/context-compress"

echo "安装 claude-context-guardian..."

mkdir -p "${SCRIPTS_DIR}"
mkdir -p "${SKILL_DIR}"

cp "${SCRIPT_DIR}/scripts/context_statusline.py" "${SCRIPTS_DIR}/"
cp "${SCRIPT_DIR}/scripts/context_hook.py" "${SCRIPTS_DIR}/"
cp "${SCRIPT_DIR}/scripts/context_write_memory.py" "${SCRIPTS_DIR}/"
cp "${SCRIPT_DIR}/scripts/context_update_status.py" "${SCRIPTS_DIR}/"
chmod +x "${SCRIPTS_DIR}"/context_*.py

cp "${SCRIPT_DIR}/skills/context-compress/SKILL.md" "${SKILL_DIR}/"

echo "脚本已安装到: ${SCRIPTS_DIR}"
echo "Skill 已安装到: ${SKILL_DIR}"
echo
echo "请手动合并以下配置到 ${CLAUDE_DIR}/settings.json:"
echo "  - statusLine"
echo "  - hooks.UserPromptSubmit"
echo
echo "完整示例见: ${SCRIPT_DIR}/settings.example.json"
echo "安装完成。"
