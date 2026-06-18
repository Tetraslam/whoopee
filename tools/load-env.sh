#!/usr/bin/env bash
# load-env.sh — resolve op:// secret references into the environment at runtime.
#
# The playground keeps secrets out of plaintext .env files. Instead we commit
# `.env.op` files that contain ONLY 1Password secret references
# (op://Personal/<item>/<field>), and resolve them on demand with the
# 1Password CLI. Nothing secret ever lands on disk or in git.
#
# Two layers, applied in order (later overrides earlier):
#   1. GLOBAL:   <repo-root>/.env.op        — shared across all toys
#   2. PER-PATH: <toy-dir>/.env.op          — toy-specific overrides
#
# USAGE
#   # Run a command with secrets injected (the common case):
#   tools/load-env.sh -- python toys/foo/main.py
#   tools/load-env.sh --dir toys/foo -- pnpm dev
#
#   # Or source it to load into your current shell:
#   source tools/load-env.sh
#
# Requires: op (1Password CLI) signed in. See repo AGENTS.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_target_dir=""
_cmd=()
# Parse args: optional --dir <path>, then `-- <command...>`.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) _target_dir="$2"; shift 2 ;;
    --) shift; _cmd=("$@"); break ;;
    *) echo "load-env: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

if ! command -v op >/dev/null 2>&1; then
  echo "load-env: 1Password CLI 'op' not found on PATH." >&2
  exit 1
fi

# Collect the .env.op files to apply, global first then per-path.
_files=()
[[ -f "$REPO_ROOT/.env.op" ]] && _files+=("$REPO_ROOT/.env.op")
if [[ -n "$_target_dir" && -f "$_target_dir/.env.op" ]]; then
  _files+=("$_target_dir/.env.op")
fi

# Build a combined env-file (op:// references) and let `op run` resolve it.
_combined="$(mktemp)"
trap 'rm -f "$_combined"' EXIT
for f in "${_files[@]:-}"; do
  [[ -n "$f" ]] && cat "$f" >> "$_combined" && echo >> "$_combined"
done

if [[ ${#_cmd[@]} -gt 0 ]]; then
  # Resolve references and exec the command with them injected (in-memory only).
  exec op run --no-masking=false --env-file="$_combined" -- "${_cmd[@]}"
else
  # Sourced mode: export resolved vars into the current shell.
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "load-env: no command given. Either pass '-- <cmd>' or 'source' this script." >&2
    exit 2
  fi
  while IFS='=' read -r key val; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key"="$val"
  done < <(op run --env-file="$_combined" -- env | grep -F -f <(sed -E 's/=.*//' "$_combined"))
  echo "load-env: secrets loaded into shell from ${#_files[@]} file(s)."
fi
