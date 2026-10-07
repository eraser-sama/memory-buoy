---
name: context-compress
description: 上下文压缩与恢复。触发词：【压缩上下文】/ [COMPRESS]、【继续】/ [RESUME]（大小写不敏感）。用户输入【压缩上下文】或 [COMPRESS] 时，把任务状态落盘到项目级记忆文件，提示用户手动 /compact；用户压缩后输入【继续】或 [RESUME] 时，读取记忆文件并接着干。
---

# 🧠 上下文压缩 Skill

## 触发方式

本 Skill 的首选触发路径是由 UserPromptSubmit Hook 检测消息里的触发标记后，通过 additionalContext 注入强指令。

触发标记（中英双语，大小写不敏感）：

- 压缩：【压缩上下文】 / [COMPRESS]
- 恢复：【继续】 / [RESUME]
- 单独输入 compress / resume（不带方括号）不触发。
- 单独的“继续”“请继续”不触发。

Fallback：若未收到 Hook 注入（Hook 未配置、换机器、Hook 异常），用户直接输入上述任一触发标记时，模型同样按下方流程执行。

- 【压缩上下文】：触发落盘 + 提示用户手动 /compact。
- 【继续】：压缩后恢复阶段触发，读取记忆文件并继续。
- 单独的“继续”“请继续”不触发。

## 脚本位置

脚本目录：~/.claude/skills/context-compress/scripts/

- context_statusline.py：状态栏，读 payload、写缓存、显示占用。
- context_hook.py：Hook，检测触发词、读缓存、门控、注入指令。
- context_write_memory.py：写入记忆文件，生成 front matter，维护 latest.md。
- context_update_status.py：恢复成功后更新 status。

## 压缩流程（收到 Hook 注入的【压缩上下文】指令时）

1. Hook 已在缓存中读到占用率，会按占用率注入“直接执行 / 询问 / 拒绝 / 占用率未知”四档指令之一。
2. 若指令为“直接执行”：
   - 模型只准备正文内容，包含五节：任务、已完成、关键参数、待完成、下一步。
   - 正文写入临时文件，例如 ~/claude_tmp/context_body_<session_id>.md（多会话时带 session 后缀，避免覆盖）。
   - 调用脚本落盘：

     python3 ~/.claude/skills/context-compress/scripts/context_write_memory.py --project-root <项目根> --session-id <session_id> --body <正文文件路径>

   - 脚本自动生成 front matter、更新 latest.md、备份轮换、原子写。
   - 模型禁止手写 YAML front matter。
3. 落盘后输出：已落盘，请执行 /compact，然后说【继续】。
4. 用户手动执行 /compact。
5. 用户输入【继续】。

## 恢复流程（收到 Hook 注入的【继续】指令时）

1. Hook 已做粗筛，通过则注入强指令，附带记忆文件路径；模型仅复核。
2. 模型读取记忆文件：
   - front matter 用完整 YAML 解析（yaml.safe_load）。
   - 正文按需读取。
3. 检查 status：
   - pending：继续。
   - consumed：正常路径下不会走到（Hook 已在粗筛阶段拦住并注入提示）；仅当用户绕过 Hook 直接触发时才可能遇到。遇到时提示“记忆已消费”，按普通对话处理。
4. 检查 saved_at 是否超过 24 小时。
   - 超过：提醒“记忆较旧，是否确认恢复”（不自动改状态）。
   - 阈值 24 小时由模型侧判断，脚本不做硬编码。
5. 读取“下一步”，开始执行。
6. 执行成功后，调用脚本更新状态：

   python3 ~/.claude/skills/context-compress/scripts/context_update_status.py <记忆文件路径> consumed

   - 脚本只修改 front matter 里的 status 和 resumed_at。
   - 脚本失败按报错三要素汇报，不假装成功。
   - 执行失败则保持 pending，允许重试。
7. 恢复不受压缩冷却限制。

### 恢复侧的安全边界

“直接继续”只针对普通任务步骤。涉及系统底层修改、删除 / 移动 / 覆盖文件、安装 / 卸载软件、任何 CLAUDE.md【人类复核】红线覆盖的操作，必须先向用户说明并确认。

被安全边界拦下、等确认时状态保持 pending；用户确认并执行成功后才改 consumed。

## 记忆文件格式

---
schema: 1
project: /path/to/project
status: pending
saved_at: 2026-10-06T14:30:00+08:00
saved_by: session-abc123
resumed_at: ''
---

## 任务
...
## 已完成
...
## 关键参数
...
## 待完成
...
## 下一步
...

- front matter 由 context_write_memory.py 用 yaml.safe_dump 生成，模型不手写。
- 正文由模型准备，作为输入传给脚本。
- saved_at、resumed_at 为 ISO 8601 带时区。
- 正文中间不要出现第二个 ---。

## 多项目与多会话

- 记忆文件放 <项目根>/.claude/context-memory/。
- 文件名优先 <session_id>.md；session_id 不稳定时用 <时间戳>_<随机6>.md。
- 项目级 latest.md 记录最近一次记忆，恢复时第一入口。
- session_id 在手动 /compact 后不变；Auto-compact 待验证。
- 项目匹配用 realpath 规范化后比对。

## 约束

- 模型不直接读 payload，不自己算占用率。
- Hook 只读不改；状态写入由模型层调用脚本执行。
- Hook 只用正则扫 front matter，不做完整 YAML 解析。
- 与 CLAUDE.md 冲突时，以 CLAUDE.md 全文为准。