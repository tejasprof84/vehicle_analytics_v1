#!/usr/bin/env bash
# Phase 4: REST API + built React dashboard on http://<host>:8000
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR"
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
