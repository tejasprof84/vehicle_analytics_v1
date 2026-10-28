#!/usr/bin/env bash
# Phase 2+3: run the DeepStream pipeline (reads RTSP, writes events to PostgreSQL)
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR/deepstream"
exec python3 app.py --uri "$RTSP_INPUT" --db-url "$DATABASE_URL" "$@"
