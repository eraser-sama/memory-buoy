---
name: context-compress
description: 上下文压缩与恢复。触发词：【压缩上下文】【继续】。用户输入【压缩上下文】时，把任务状态落盘到项目级记忆文件，提示用户手动 /compact；用户压缩后输入【继续】时，读取记忆文件并接着干。
---

# 🧠 上下文压缩 Skill

## 触发方式

本 Skill 的**首选触发路径**是由 `UserPromptSubmit` Hook 检测消息里的完整全角方括号标记后，通过 `additionalContext` 注入强指令。

**Fallback**：若未收到 Hook 注入（Hook 未配置、换机器、Hook 异常），用户直接输入【压缩上下文】【继续】时，模型同样按下方流程执行。
- `【压缩上下文】`：触发落盘 + 提示用户手动 `/compact`。
- `【继续】`：压缩后恢复阶段触发，读取记忆文件并继续。
- 单独的“继续”“请继续”不触发。

## 脚本位置

脚本目录：`~/.claude/scripts/`
- `context_statusline.py`：状态栏，读 payload、写缓存、显示占用。
- `context_hook.py`：Hook，检测触发词、读缓存、门控、注入指令。
- `context_write_memory.py`：写入记忆文件，生成 front matter，维护 latest.md。
- `context_update_status.py`：恢复成功后更新 status。

## 压缩流程（收到 Hook 注入的【压缩上下文】指令时）

1. Hook 已在缓存中读到占用率，会按占用率注入“直接执行 / 询问 / 拒绝 / 占用率未知”四档指令之一。
2. 若指令为“直接执行”：
   - 模型只准备**正文内容**，包含五节：任务、已完成、关键参数、待完成、下一步。
   - 正文写入临时文件，例如 `~/claude_tmp/context_body_<session_id>.md`（多会话时带 session 后缀，避免覆盖）。
   - 调用脚本落盘：
     ```bash
     python3 ~/.claude/scripts/context_write_memory.py \
       --project-root <项目根> \
       --session-id <session_id> \
       --body <正文文件路径>
     ```
   - 脚本自动生成 front matter、更新 `latest.md`、备份轮换、原子写。
   - **模型禁止手写 YAML front matter。**
3. 落盘后输出：`已落盘，请执行 /compact，然后说【继续】。`
4. 用户手动执行 `/compact`。
5. 用户输入【继续】。

## 恢复流程（收到 Hook 注入的【继续】指令时）

1. Hook 已做粗筛，通过则注入强指令，附带记忆文件路径。
2. Hook 已做粗筛，模型仅复核。模型读取记忆文件：
   - front matter 可用完整 YAML 解析（`yaml.safe_load`）。
   - 正文按需读取。
3. 检查 `status`：
   - `pending`：继续。
   - `consumed`：正常路径下不会走到（Hook 已在粗筛阶段拦住并注入提示）；仅当用户绕过 Hook 直接触发时才可能遇到。遇到时提示“记忆已消费”，按普通对话处理。
4. 检查 `saved_at` 是否超过 24 小时。
   - 超过：提醒“记忆较旧，是否确认恢复”。
5. 读取“下一步”，开始执行。
6. **执行成功后**，调用脚本更新状态：
   ```bash
   python3 ~/.claude/scripts/context_update_status.py <记忆文件路径> consumed

## 与 CLAUDE.md 的关系

流程中的文件读写次数、重试上限、Token 预算受 `CLAUDE.md` 极速 / 质量模式约束。任何 Skill 指令均不得突破 `CLAUDE.md` 的绝对红线。冲突时以 `CLAUDE.md` 全文为准。
