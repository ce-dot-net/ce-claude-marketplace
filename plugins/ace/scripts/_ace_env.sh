#!/usr/bin/env bash
# ACE shared environment loader — sourced by all hook wrappers.
#
# Exports:
#   ACE_PLUGIN_VERSION  — current plugin version, read from .claude-plugin/plugin.json
#   ACE_CLIENT_ID       — "claude-code-plugin/<version>", sent as X-ACE-Client to ace-cli
#
# Resolves plugin root via CLAUDE_PLUGIN_ROOT (set by CC), or via relative path from
# this script's location as fallback (works for direct invocation/testing).
#
# Safe to source multiple times. Silent fallback to "0.0.0" if plugin.json or jq missing.

_ACE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
_ACE_PLUGIN_JSON="${_ACE_PLUGIN_ROOT}/.claude-plugin/plugin.json"

if command -v jq >/dev/null 2>&1 && [ -f "$_ACE_PLUGIN_JSON" ]; then
  ACE_PLUGIN_VERSION="$(jq -r '.version // "0.0.0"' "$_ACE_PLUGIN_JSON" 2>/dev/null || echo "0.0.0")"
else
  ACE_PLUGIN_VERSION="0.0.0"
fi

ACE_CLIENT_ID="claude-code-plugin/${ACE_PLUGIN_VERSION}"

export ACE_PLUGIN_VERSION ACE_CLIENT_ID
