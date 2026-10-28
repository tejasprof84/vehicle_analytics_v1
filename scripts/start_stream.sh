#!/usr/bin/env bash
# Phase 1: loop an MP4 traffic video into MediaMTX as a live RTSP stream.
#
#   bash scripts/start_stream.sh                 # uses $INPUT_VIDEO from .env
#   bash scripts/start_stream.sh my_traffic.mp4  # any other video
#
# -re           read at native frame rate (behave like a live camera)
# -stream_loop  loop forever
# libx264       re-encode to plain H.264 (no B-frames) so every decoder is happy
# -rtsp_transport tcp   reliable delivery to MediaMTX
#
# Verify in VLC: Media > Open Network Stream > rtsp://<host>:8554/traffic
set -euo pipefail
source "$(dirname "$0")/common.sh"

VIDEO="${1:-$INPUT_VIDEO}"
echo "Publishing $VIDEO -> rtsp://127.0.0.1:8554/traffic"

exec ffmpeg -hide_banner -loglevel warning \
  -re -stream_loop -1 -i "$VIDEO" \
  -an -c:v libx264 -preset veryfast -tune zerolatency -bf 0 -g 30 -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/traffic
