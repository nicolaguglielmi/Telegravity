# Changelog

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
