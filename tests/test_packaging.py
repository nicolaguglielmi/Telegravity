"""Release-consistency checks.

The version is bumped in exactly one place (``telegravity/__version__.py``,
which pyproject's hatch config reads); the plugin manifests must agree with it
or marketplace users are never offered the update.
"""

import json
from pathlib import Path

from telegravity import __version__

ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text())


def test_plugin_manifest_version_matches_package():
    assert _load(".claude-plugin/plugin.json")["version"] == __version__


def test_marketplace_carries_no_second_version_copy():
    market = _load(".claude-plugin/marketplace.json")
    entry = market["plugins"][0]
    assert entry["name"] == "telegravity"
    assert entry["source"] == "./"
    assert "version" not in entry
    assert "version" not in market.get("metadata", {})


def test_plugin_mcp_server_uses_console_script():
    manifest = _load(".claude-plugin/plugin.json")
    server = manifest["mcpServers"]["telegravity"]
    assert server["command"] == "telegravity"


def test_no_project_scope_mcp_json():
    """A root .mcp.json would auto-spawn a second poller for anyone opening
    this repo in Claude Code — the plugin manifest owns the MCP config."""
    assert not (ROOT / ".mcp.json").exists()
