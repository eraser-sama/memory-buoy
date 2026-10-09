# 🧠 memory-buoy

为 Claude Code 提供上下文实时监控与压缩/恢复闭环的工具集。

## 解决什么问题

Claude Code 会话变长后，上下文会被填满，模型开始变傻、变慢，最终报错。官方 /compact 能压缩，但压缩前的任务状态会丢失，压缩后不知道怎么接着干。

本项目提供三层能力：

1. 实时监控：状态栏实时显示上下文占用百分比，0–60% 黄、60–80% 橙、80%+ 红并挂 ⚠️。
2. 压缩落盘：用户输入【压缩上下文】，任务状态落盘到项目级记忆文件，然后提示用户执行 /compact。
3. 恢复续接：用户输入【继续】，自动读取记忆文件，从上次的“下一步”接着干。

## 安装

git clone https://github.com/eraser-sama/memory-buoy.git
cd memory-buoy
bash install.sh

install.sh 会把脚本复制到 ~/.claude/skills/context-compress/scripts/，把 Skill 复制到 ~/.claude/skills/context-compress/，并提示你手动合并 settings.example.json 到 ~/.claude/settings.json。

## 配置

在 ~/.claude/settings.json 中加入 statusLine 和 hooks 配置，指向 context_statusline.py 和 context_hook.py。完整示例见 settings.example.json。

## 使用

1. 状态栏：自动显示 📊 Context: 42% (~84k/200k)。
2. 压缩：输入【压缩上下文】，模型落盘后提示你执行 /compact。
3. 恢复：/compact 后输入【继续】，模型读取记忆文件接着干。

## 新功能

- **主动提醒** — `CONTEXT_PROMPT_AT`：上下文占用达到阈值时，Hook 会自动提醒你【压缩上下文】。默认关闭，设为 80 即开启。提醒冷却 24 小时，可用 `CONTEXT_PROMPT_COOLDOWN` 调整。
- **落盘结构校验** — 写入记忆文件时，会检查“下一步”章节是否存在且非空（含 TODO / TBD 等占位符会拒绝），写完后还会读回文件验证有效性。
- **记忆标记** — 状态栏在有未消费的 pending 记忆时显示 📌。
- **多 pending 清单** — 【继续】时如果项目里有多个待恢复记忆，不再只读最新的，而是列出清单（按时间从新到旧）让你挑选。

## 跨会话恢复（话题继承）

记忆文件按项目根匹配，不绑定 session_id。旧话题压缩落盘后，在同一个项目里新开会话、输入【继续】，模型会读取 latest.md，从旧话题的"下一步"接着干。相比原地 /compact，这种方式能彻底清零上下文，让模型满血复活，同时不丢任务进度。

## 依赖

- Python 3.10+
- PyYAML（python3 -m pip install PyYAML）
- Claude Code 2.1.283 或以上

## 记忆文件

存放在 <项目根>/.claude/context-memory/，YAML front matter + Markdown 正文。latest.md 记录最近一次记忆文件，恢复时第一入口。

## 已实测结论

- statusLine payload 含 used_percentage、workspace.project_dir、session_id、transcript_path。
- Hook payload 只有 prompt、session_id、transcript_path、cwd，不含 used_percentage。
- 手动 /compact 后 session_id 不变，used_percentage 归 0。
- current_usage 不含本轮 output_tokens。

## 已知限制

- Hook 必须读 statusLine 缓存拿占用率。
- Auto-compact 是否换 session_id 待验证。
- 时间戳默认 UTC，可通过 CONTEXT_TZ_OFFSET 环境变量调整为东八区等（如 CONTEXT_TZ_OFFSET=8）。

## 许可

MIT
## 状态栏的 ? 标记

状态栏显示 200k 且模型 ID 不以 claude- 开头时，末尾会加一个 ?，提示该上限可能不准确。

例如：📊 Context: 12% (~23k/200k) ?

这表示模型是第三方模型，Claude Code 回退到了默认 200K。如果模型实际支持更大窗口，用 CLAUDE_CODE_MAX_CONTEXT_TOKENS 覆盖。
