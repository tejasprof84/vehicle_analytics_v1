#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-time setup inside the DeepStream 7.1 container
# (nvcr.io/nvidia/deepstream:7.1-triton-multiarch) or on an Ubuntu 22.04
# machine that already has DeepStream 7.1 installed. Run as root.
#
# Installs: FFmpeg, PostgreSQL, MediaMTX, DeepStream Python bindings (pyds),
#           Python packages, Node.js 20, and builds the React dashboard.
# ---------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR"
export DEBIAN_FRONTEND=noninteractive

echo "==> [1/7] System packages"
apt-get update
apt-get install -y --no-install-recommends \
  ffmpeg postgresql postgresql-contrib tmux curl wget git ca-certificates \
  python3-pip python3-venv python3-gi python3-gst-1.0 \
  gir1.2-gst-rtsp-server-1.0 libgstrtspserver-1.0-0 gstreamer1.0-rtsp

echo "==> [2/7] DeepStream extra plugins/codecs"
if [[ -f "$DS_ROOT/user_additional_install.sh" ]]; then
  (cd "$DS_ROOT" && bash user_additional_install.sh) || echo "WARN: user_additional_install.sh failed (usually safe to ignore)"
fi

echo "==> [3/7] DeepStream Python bindings (pyds 1.2.0 for DeepStream 7.1)"
if ! python3 -c "import pyds" 2>/dev/null; then
  pip3 install "https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/releases/download/v1.2.0/pyds-1.2.0-cp310-cp310-linux_x86_64.whl"
fi

echo "==> [4/7] Python packages (pipeline + API)"
pip3 install -r deepstream/requirements.txt -r backend/requirements.txt

echo "==> [5/7] MediaMTX"
if [[ ! -x bin/mediamtx ]]; then
  mkdir -p bin
  URL=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
        | grep -o 'https://[^"]*linux_amd64\.tar\.gz' | head -n1)
  echo "Downloading $URL"
  curl -L "$URL" | tar -xz -C bin mediamtx
fi

echo "==> [6/7] Node.js 20 + dashboard build"
if ! command -v node >/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
(cd frontend && npm install && npm run build)

echo "==> [7/7] Database + primary detector config"
bash scripts/init_db.sh
python3 scripts/prepare_pgie_config.py

echo
echo "Setup complete. Next:"
echo "  1. Train/export the colour classifier:  see color_classifier/README.md"
echo "  2. Start everything:                    bash scripts/run_all.sh"
