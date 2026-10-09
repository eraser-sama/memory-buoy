# memory-buoy

Real-time context monitoring and compress/resume workflow for Claude Code.

## What it solves

Long Claude Code sessions fill up the context window, and the model gets slow and forgetful. The built-in /compact helps, but the task state is lost afterwards.

This project adds three layers:

1. Real-time monitoring: a status line showing context usage. Yellow 0-60%, orange 60-80%, red 80%+ with a warning.
2. Compress to disk: user types [COMPRESS] , the task state is saved to a project-level memory file, then the user runs /compact.
3. Resume: after /compact, user types [RESUME], and the model reads the memory file and continues from the last step.

## Install

    git clone <repo>
    cd memory-buoy
    bash install.sh

install.sh copies scripts to ~/.claude/skills/context-compress/scripts/ and the skill to ~/.claude/skills/context-compress/, then tells you to merge settings.example.json into ~/.claude/settings.json.

## Configuration

Add statusLine and hooks.UserPromptSubmit to ~/.claude/settings.json, pointing at context_statusline.py and context_hook.py. See settings.example.json.

## Usage

1. Status line: shows 📊 Context: 42% (~84k/200k) automatically.
2. Compress: type [COMPRESS] (case-insensitive). The model saves state and tells you to run /compact.
3. Resume: after /compact, type [RESUME] (case-insensitive). The model reads the memory file and continues.

## New features

- **Proactive reminder** — `CONTEXT_PROMPT_AT`: when context usage reaches the threshold, the hook automatically reminds you to [COMPRESS]. Off by default; set it to 80 to enable. Reminders are throttled to once per 24h per session; adjust with `CONTEXT_PROMPT_COOLDOWN`.
- **Write-time validation** — when saving a memory file, the "next step" section is checked to exist and be non-empty (placeholder text like TODO / TBD is rejected), and the file is re-read after writing to verify it is valid.
- **Memory marker** — the status line shows a 📌 when there is unconsumed pending memory in the project.
- **Multiple pending memories** — on [RESUME], if the project has more than one pending memory, the hook lists them (newest first) so you can pick which to restore, instead of always reading the latest.

## Resume across sessions (topic handover)

Memory files are matched by project root, not by session id. After you compress an old task, you can start a *new* session in the same project and type [RESUME] — the model reads latest.md and continues from the old task's "next step". Compared to an in-place /compact, this fully clears the context window — the model starts fresh — without losing task progress.

## Requirements

- Python 3.10+
- PyYAML (python3 -m pip install PyYAML)
- Claude Code 2.1.283 or newer

## Memory file

Stored under <project>/.claude/context-memory/, with YAML front matter and Markdown body. latest.md points to the most recent memory file and is the first lookup entry when resuming.

## Verified behavior

- statusLine payload includes used_percentage, workspace.project_dir, session_id, transcript_path.
- Hook payload only has prompt, session_id, transcript_path, cwd; no used_percentage.
- Manual /compact keeps session_id unchanged and resets used_percentage to 0.
- current_usage does not include this turn's output_tokens.

## Known limitations

- Hook must read the statusLine cache to get usage.
- Whether Auto-compact changes session_id is not yet verified.
- Timestamps default to UTC; override with CONTEXT_TZ_OFFSET env var.

## License

MIT

## The ? marker in the status line

When the status line shows 200k and the model id does not start with claude-, a ? is appended to indicate the limit may be inaccurate.

Example: 📊 Context: 12% (~23k/200k) ?

This means the model is a third-party model and Claude Code fell back to the default 200K. If the model actually supports a larger window, override it with CLAUDE_CODE_MAX_CONTEXT_TOKENS.
