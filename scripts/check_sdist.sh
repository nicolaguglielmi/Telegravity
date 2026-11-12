#!/usr/bin/env bash
# Inspect a built sdist before it can reach PyPI.
#
# The repository doubles as an agent workspace: `.claude/` can hold git
# worktrees, i.e. entire copies of the repo at arbitrary past states, and
# `data/` holds the runtime state of whoever ran the server locally. Neither
# must ever ship. We also refuse anything that looks like a real bot token or
# a personal email address, because a published version can never be
# re-uploaded.
#
# Usage: scripts/check_sdist.sh [dist/*.tar.gz]
set -euo pipefail

sdist="${1:-}"
if [[ -z "$sdist" ]]; then
    shopt -s nullglob
    candidates=(dist/*.tar.gz)
    if [[ ${#candidates[@]} -ne 1 ]]; then
        echo "::error::expected exactly one dist/*.tar.gz, found ${#candidates[@]}" >&2
        exit 1
    fi
    sdist="${candidates[0]}"
fi

scan_dir="$(mktemp -d)"
trap 'rm -rf "$scan_dir"' EXIT
tar -xzf "$sdist" -C "$scan_dir"

fail=0

if find "$scan_dir" -type d \( -name ".claude" -o -name "worktrees" -o -name "data" \) | grep -q .; then
    echo "::error::sdist contains a directory that must never ship"
    fail=1
fi

if grep -rIEq "[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.[a-z]+" "$scan_dir"; then
    echo "::error::sdist contains a personal email address"
    fail=1
fi

if grep -rIEq "TELEGRAM_TOKEN[[:space:]]*=[[:space:]]*[0-9]{8,}:[A-Za-z0-9_-]{30,}" "$scan_dir"; then
    echo "::error::sdist contains what looks like a real bot token"
    fail=1
fi

if [[ "$fail" == "0" ]]; then
    echo "artifacts clean: $sdist"
fi
exit "$fail"
