#!/usr/bin/env bash
# Creates a PRIVATE GitHub repo "anyhouse-video-studio" from this folder and pushes it (needs git + GitHub CLI).
set -e
cd "$(dirname "$0")"
command -v git >/dev/null || { echo "Install git first"; exit 1; }
[ -d .git ] || { git init -b main; git add -A; git commit -m "Initial commit: AnyHouse Video Studio (engine, web UI, MCP server, agent skill)"; }
if command -v gh >/dev/null; then
  gh auth status >/dev/null 2>&1 || gh auth login
  gh repo create anyhouse-video-studio --private --source . --remote origin --push
else
  echo "GitHub CLI not found. Create an empty private repo at https://github.com/new then:"
  echo "  git remote add origin https://github.com/YOUR_USER/anyhouse-video-studio.git && git push -u origin main"
fi
