#!/usr/bin/env bash
# Start the whole system in one tmux session with four panes:
#
#   +---------------------+---------------------+
#   | MediaMTX            | FFmpeg -> RTSP      |
#   +---------------------+---------------------+
#   | DeepStream pipeline | API + dashboard     |
#   +---------------------+---------------------+
#
# Attach: tmux attach -t vehicle      Stop: tmux kill-session -t vehicle
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR"

service postgresql start >/dev/null
tmux kill-session -t vehicle 2>/dev/null || true

tmux new-session  -d -s vehicle -n main "bash scripts/start_mediamtx.sh"
tmux split-window -h -t vehicle:main "sleep 2; bash scripts/start_stream.sh"
tmux split-window -v -t vehicle:main.0 "sleep 5; bash scripts/start_pipeline.sh; read"
tmux split-window -v -t vehicle:main.1 "bash scripts/start_backend.sh"
tmux select-layout -t vehicle:main tiled

echo "Started. Attach with:  tmux attach -t vehicle"
echo "Dashboard: http://localhost:8000   Raw RTSP: rtsp://localhost:8554/traffic"
echo "Annotated: rtsp://localhost:8554/processed   HLS: http://localhost:8888/processed/"
