#!/usr/bin/env bash
# Phase 1: start the MediaMTX video broker (RTSP :8554, HLS :8888, WebRTC :8889)
#
# Docker alternative (any machine):
#   docker run --rm -it --network=host -v $PWD/mediamtx/mediamtx.yml:/mediamtx.yml bluenviron/mediamtx
set -euo pipefail
source "$(dirname "$0")/common.sh"
exec "$REPO_DIR/bin/mediamtx" "$REPO_DIR/mediamtx/mediamtx.yml"
