---
name: telegravity-active-mode
description: >-
  Drive this coding agent remotely from Telegram via the Telegravity MCP server.
  Use when the user asks to "enter Active Mode", "listen to Telegram", "let me
  control you from my phone", or to act on instructions arriving over Telegram.
---

# Telegravity — Active Mode

Telegravity is an MCP server that bridges Telegram and you (the local agent).
The user sends instructions from Telegram; you pull and execute them. Nothing is
pushed — **you must call the tools** to receive work.

## The loop

When asked to enter Active Mode, run this loop until the user says **stop**:

1. `register_agent_activity("waiting", "listening on Telegram")`.
2. Call `wait_for_remote_instruction(120)`. It blocks until a message arrives or
   times out (returns an empty list on timeout).
3. On **timeout (empty)** → call `wait_for_remote_instruction(120)` again.
4. On **message(s)** → for each instruction:
   - Determine the target project (see *Workspace routing* below).
   - `register_agent_activity("executing", "<short description>")`.
   - Do the work.
   - `send_message("<result / what you did / any questions>")` to report back.
   - `update_conversation(...)` to journal progress for the dashboard.
5. Go back to step 1.

If the loop ever stops (the IDE caps a turn), the user just re-issues
"continue Active Mode" — queued messages are not lost; they wait in the buffer.

## Workspace routing — IMPORTANT

A Telegram **workspace** is the project the user wants you to work on. Telegravity
**cannot** change the folder open in the IDE, so the workspace is delivered to
**you** instead, two ways:

- Queued instructions are **tagged**:
  `[time] 👤 Telegram (workspace=MoliseLive, dir=/Users/nicola/Dev/MoliseLive): <instruction>`
- `get_state()` reports `WORKSPACE`, `WORKSPACE_DIR`, and `AVAILABLE WORKSPACES`.

Honor the tagged directory. To **act on a project that is NOT the folder open in
your IDE**, use Telegravity's workspace-rooted tools (they run in the Telegravity
process, so they reach the selected directory even when your own file tools are
confined to the open project):

- `run_command(command, timeout_sec=30)` — shell command in the workspace dir.
- `read_file(rel_path)` — read a file under the workspace dir.
- `write_file(rel_path, content)` — write a file under the workspace dir.

If the active workspace **is** the folder open in your IDE, prefer your own
native tools; otherwise use the three tools above.

You can also `set_active_workspace(name)` to switch the focus yourself (e.g. the
user says "switch to Klaris"), then operate on its `WORKSPACE_DIR`.

## Gating & safety

- `run_command` needs `ENABLE_SHELL_EXEC=1`, `read_file` needs `ENABLE_FILE_VIEW=1`,
  `write_file` needs `ENABLE_FILE_WRITE=1`. If a tool returns "disabled", tell the
  user which env var to set; don't try to work around it.
- All three are **jailed** to the active workspace directory — a `rel_path` that
  escapes it is rejected.
- Only act on instructions from the single authorized user (Telegravity enforces
  this); do exactly what was asked.

## Tools reference

| Tool | Purpose |
|------|---------|
| `wait_for_remote_instruction(t)` | Long-poll up to `t`s for the next message (Active Mode) |
| `check_telegram_updates()` | Drain queued messages without blocking |
| `send_message(text)` | Reply to the user on Telegram |
| `get_state()` | Workspace, dir, conversations, recent buffer |
| `set_active_workspace(name)` | Switch the active workspace |
| `run_command(cmd, timeout_sec)` | Run a shell command in the workspace dir |
| `read_file(rel_path)` | Read a file under the workspace dir |
| `write_file(rel_path, content)` | Write a file under the workspace dir |
| `register_agent_activity(status, detail)` | Heartbeat for the dashboard |
| `update_conversation(...)` | Journal a rich progress entry |
