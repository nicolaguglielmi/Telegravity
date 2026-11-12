# Changelog

## Unreleased

### Fixed
- **Duplicate instances no longer fight over Telegram updates.** When two MCP
  clients (e.g. the Antigravity hub and IDE, sharing one `mcp_config.json`)
  each spawn `telegravity` with the same token, both used to long-poll
  `getUpdates` — Telegram 409'd and updates were randomly split between the
  processes, silently losing instructions. Now an advisory `flock` on
  `<DATA_DIR>/poller.lock` elects a single poller: the holder polls as before;
  a standby instance keeps serving MCP tools (`send_message` works, the
  receive tools return an explanatory note instead of competing) and retries
  the lock every 10 s so it takes over when the holder exits. POSIX-only
  (`fcntl`); on Windows the guard is a no-op.
- **A wrong `TELEGRAM_TOKEN` now fails loudly.** Startup calls `get_me` and
  exits with status 2 and an actionable message. Previously the token was
  never checked: `set_my_commands` and the startup card both swallow Telegram
  errors, so a bad token produced a process that looked perfectly healthy —
  MCP tools answering, no crash — while the bot simply never existed. A
  startup card that can't be delivered now names the chat id and says to send
  `/start`, since that one usually means `AUTHORIZED_CHAT_ID` is wrong or the
  chat was never opened.
- **Long agent messages are no longer lost.** `send_message` splits text that
  exceeds Telegram's per-message cap across several messages (preferring line
  breaks, keyboard under the last one) instead of having the whole send
  rejected. The limit is counted in UTF-16 code units, the way Telegram counts
  it, so an emoji-dense report splits correctly. MarkdownV2 screens can't be
  chunked safely — a split could land inside an escape sequence — so the
  conversation ping, the activity feed and the interaction detail trim their
  unbounded fields instead.
- **The dashboard pointed at a file the server never reads.** The onboarding
  tour and both "no workspaces yet" screens said to edit `data/workspaces.txt`;
  the real file is `<DATA_DIR>/workspaces.txt` (`~/.telegravity/workspaces.txt`
  by default). They now show the live path, resolved per render so a
  `TELEGRAVITY_DATA_DIR` arriving from a `.env` is reflected.

### Added
- **CI on every push and pull request** (`.github/workflows/ci.yml`): the test
  suite across Python 3.11–3.14, a lint gate (`ruff`), and a packaging build
  check. Previously tests only ran on a `v*` tag push, i.e. at release time.

## 0.3.1 — 2026-08-18

### Changed
- Maintainer contact now points at the GitHub profile and the issue tracker
  instead of a plain-text email address in the package metadata and the
  plugin manifests. Functionally identical to 0.3.0, which was removed from
  PyPI; a published version can never be re-uploaded, hence the bump.

## 0.3.0 — 2026-08-06

### Fixed
- **Works with MCP SDK 2.0.** The SDK removed `mcp.server.fastmcp`; Telegravity
  now uses `mcp.server.MCPServer` and falls back to `FastMCP` on mcp 1.x. The
  broken `mcp[fastmcp]` dependency extra is gone (`mcp>=1.3` — the floor where
  the fallback supports server instructions and async resources).
- **`TELEGRAVITY_DATA_DIR` now works from a `.env` file.** Paths re-resolve
  after each `load_dotenv` (`paths.refresh()`); previously the documented
  option was silently ignored unless exported as a real environment variable.

### Added
- **Claude Code plugin packaging.** The repository now doubles as a plugin
  marketplace: `/plugin marketplace add nicolaguglielmi/Telegravity`, then
  `/plugin install telegravity` wires the MCP server, the Active Mode skill,
  and the `/telegravity:active-mode` command in one step.
- **Global config fallback.** `~/.telegravity/.env` (the data dir) is always
  layered underneath the environment and any project-local `.env`, filling in
  whatever they didn't set — so MCP clients that launch the server from an
  arbitrary directory need zero per-project setup, and an unrelated project's
  `.env` can't mask the credentials.
- `LICENSE` (MIT) and this changelog.

### Changed
- The Active Mode skill moved from `SKILL.md` to
  `skills/telegravity-active-mode/SKILL.md` (Claude Code plugin layout).
- Packaging metadata: real repository URLs, SPDX license expression,
  Python 3.13/3.14 classifiers, author contact.

### Removed
- The legacy `tasks.json` migration, which read from the process working
  directory — an MCP server can be launched from any directory, so it could
  silently ingest an unrelated project's file into the conversations store.
- Dead view renderers (`render_followup_captured`, `render_unauthorized`).

## 0.2.0 — 2026-06

- Rebuilt as Telegravity: path-aware workspaces, agent-scoped execution tools
  (`run_command` / `read_file` / `write_file`), Active Mode, onboarding tour,
  data dir moved to `~/.telegravity`.
