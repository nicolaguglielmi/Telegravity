"""Workspace discovery & resolution: map workspace labels to real project paths.

A "workspace" used to be a bare label. It now carries an *optional* filesystem
path so remote instructions and the gated executors can target the right project
directory. Paths are merged from several sources (later sources can add a path
to / override an earlier label):

1. **Antigravity project registry** — ``~/.gemini/config/projects/*.json`` gives
   ``name -> folderUri`` with zero manual setup (when auto-import is enabled).
2. **``INITIAL_WORKSPACES``** env — bare labels; path resolved from the
   auto-import map (or the base dir) if the name matches.
3. **``data/workspaces.txt``** — one entry per line, either ``Label=/abs/path``
   (explicit) or a bare ``Label``.
4. **Base-dir fallback** — when ``TELEGRAVITY_WORKSPACE_BASE`` is set, a bare
   label ``X`` with no path resolves to ``<base>/X`` if that is a directory.

Only paths that exist and are directories are kept; anything else stays a
label-without-path: still selectable in the dashboard, but not usable as an
execution target (the agent is told there is no directory for it).
"""

from __future__ import annotations

import glob
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def _uri_to_path(uri: Optional[str]) -> Optional[str]:
    """Turn a ``file://`` URI (or a bare path) into a local filesystem path."""
    if not uri:
        return None
    if uri.startswith("file://"):
        return unquote(urlparse(uri).path) or None
    return uri


def _validated_dir(raw: Optional[str]) -> Optional[str]:
    """Return the resolved absolute path iff it exists and is a directory."""
    if not raw:
        return None
    try:
        resolved = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return str(resolved) if resolved.is_dir() else None


def import_antigravity_projects(projects_dir) -> Dict[str, str]:
    """Read Antigravity's project registry into ``{name: abs_path}``.

    Skips projects whose folder no longer exists. Tolerant of malformed files.
    """
    result: Dict[str, str] = {}
    base = Path(projects_dir).expanduser()
    if not base.is_dir():
        return result
    for fp in sorted(glob.glob(str(base / "*.json"))):
        try:
            data = json.loads(Path(fp).read_text())
        except Exception as exc:  # noqa: BLE001 - registry is external/untrusted
            logger.debug("Skipping unreadable project file %s: %s", fp, exc)
            continue
        name = (data.get("name") or "").strip()
        if not name:
            continue
        uri = None
        resources = (data.get("projectResources") or {}).get("resources") or []
        for res in resources:
            if isinstance(res, dict) and res.get("folderUri"):
                uri = res["folderUri"]
                break
        path = _validated_dir(_uri_to_path(uri))
        if path:
            result[name] = path
    return result


def parse_workspaces_file(path) -> Dict[str, Optional[str]]:
    """Parse ``workspaces.txt``: ``Label=/abs/path`` or bare ``Label`` per line.

    ``#`` comments and blank lines are ignored. An explicit path that does not
    resolve to a directory is treated as no path (the label is still kept).
    """
    out: Dict[str, Optional[str]] = {}
    p = Path(path)
    if not p.exists():
        return out
    try:
        lines = p.read_text().splitlines()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed reading %s: %s", path, exc)
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            label, _, raw = line.partition("=")
            label = label.strip()
            if label:
                out[label] = _validated_dir(raw.strip())
        else:
            out[line] = None
    return out


def resolve_workspaces(
    initial_labels: Iterable[str],
    workspaces_file,
    projects_dir,
    *,
    autoimport: bool = True,
    base_dir: Optional[str] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """Merge every source into ``(sorted labels, {label: abs_path})``."""
    labels: set[str] = set()
    paths: Dict[str, str] = {}

    auto = import_antigravity_projects(projects_dir) if autoimport else {}
    for name, path in auto.items():
        labels.add(name)
        paths[name] = path

    for raw_label in initial_labels or []:
        label = (raw_label or "").strip()
        if not label:
            continue
        labels.add(label)
        if label not in paths and label in auto:
            paths[label] = auto[label]

    for label, path in parse_workspaces_file(workspaces_file).items():
        labels.add(label)
        if path:  # explicit Label=/abs/path wins
            paths[label] = path
        elif label not in paths and label in auto:
            paths[label] = auto[label]

    if base_dir:
        base = _validated_dir(base_dir)
        if base:
            for label in labels:
                if label not in paths:
                    candidate = _validated_dir(str(Path(base) / label))
                    if candidate:
                        paths[label] = candidate

    return sorted(labels), paths
