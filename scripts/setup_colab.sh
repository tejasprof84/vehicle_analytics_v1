#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-time setup on a free Google Colab T4 runtime (no Docker available).
#
# Colab runs Ubuntu 24.04 + Python 3.12 with a recent NVIDIA driver, which
# matches DeepStream 8.0 (not 7.1, which needs Ubuntu 22.04 / Python 3.10).
# So instead of the DeepStream container we install the same stack natively:
#
#   CUDA 12.8 -> TensorRT 10.9 -> DeepStream 8.0 (.deb) -> pyds 1.2.2 (cp312)
#
# The pipeline code itself is unchanged: it reads model paths from the
# installed DeepStream samples, so it adapts to the SDK version.
#
# Usage (Colab cell):  !bash scripts/setup_colab.sh      (~20-30 min)
# ---------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR"
export DEBIAN_FRONTEND=noninteractive

VENV=/opt/ds-venv                      # common.sh puts this on PATH when it exists
TRT_VERSION="10.9.0.34-1+cuda12.8"
DS_DEB="deepstream-8.0_8.0.0-1_amd64.deb"
DS_URL="https://api.ngc.nvidia.com/v2/resources/org/nvidia/deepstream/8.0/files?redirect=true&path=${DS_DEB}"
PYDS_WHL="https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/releases/download/v1.2.2/pyds-1.2.2-cp312-cp312-linux_x86_64.whl"

echo "==> [1/8] Check the machine"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
grep -q "24.04" /etc/os-release || echo "WARN: expected Ubuntu 24.04 (DeepStream 8.0 target)"

echo "==> [2/8] System packages (DeepStream 8.0 prerequisites + project tools)"
apt-get update
apt-get install -y --no-install-recommends \
  libssl3 libssl-dev libgles2-mesa-dev libgstreamer1.0-0 gstreamer1.0-tools \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav libgstreamer-plugins-base1.0-dev libgstrtspserver-1.0-0 \
  libjansson4 libyaml-cpp-dev libjsoncpp-dev protobuf-compiler libmosquitto1 \
  gcc make git wget curl ca-certificates \
  ffmpeg postgresql postgresql-contrib tmux \
  python3-venv python3-gi python3-gst-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-rtsp

echo "==> [3/8] CUDA 12.8 toolkit"
if [[ ! -d /usr/local/cuda-12.8 ]]; then
  wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
  dpkg -i cuda-keyring_1.1-1_all.deb && rm cuda-keyring_1.1-1_all.deb
  apt-get update
  apt-get install -y --no-install-recommends cuda-toolkit-12-8
else
  echo "already installed"
fi

echo "==> [4/8] TensorRT ${TRT_VERSION}"
v="$TRT_VERSION"
apt-get install -y --no-install-recommends --allow-downgrades --allow-change-held-packages \
  libnvinfer10=$v libnvinfer-plugin10=$v libnvinfer-lean10=$v libnvinfer-dispatch10=$v \
  libnvinfer-vc-plugin10=$v libnvonnxparsers10=$v \
  libnvinfer-dev=$v libnvinfer-headers-dev=$v libnvinfer-plugin-dev=$v libnvinfer-headers-plugin-dev=$v \
  libnvinfer-lean-dev=$v libnvinfer-dispatch-dev=$v libnvinfer-vc-plugin-dev=$v libnvonnxparsers-dev=$v \
  tensorrt-dev=$v

echo "==> [5/8] DeepStream 8.0 SDK"
if [[ ! -d "$DS_ROOT" ]]; then
  wget -q --show-progress -O "/tmp/${DS_DEB}" "$DS_URL"
  apt-get install -y "/tmp/${DS_DEB}"
  rm -f "/tmp/${DS_DEB}"
fi
if [[ -f "$DS_ROOT/user_additional_install.sh" ]]; then
  (cd "$DS_ROOT" && bash user_additional_install.sh) || echo "WARN: user_additional_install.sh failed (usually safe to ignore)"
fi
ldconfig

echo "==> [6/8] Python 3.12 venv with pyds 1.2.2 (sees the apt GStreamer bindings)"
[[ -d "$VENV" ]] || /usr/bin/python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q "$PYDS_WHL" -r deepstream/requirements.txt -r backend/requirements.txt

echo "==> [7/8] MediaMTX + dashboard build"
if [[ ! -x bin/mediamtx ]]; then
  mkdir -p bin
  URL=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
        | grep -o 'https://[^"]*linux_amd64\.tar\.gz' | head -n1)
  curl -L "$URL" | tar -xz -C bin mediamtx
fi
if ! command -v node >/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
(cd frontend && npm install --no-audit --no-fund && npm run build)

echo "==> [8/8] Database + primary detector config"
bash scripts/init_db.sh
"$VENV/bin/python" scripts/prepare_pgie_config.py
"$VENV/bin/python" -c "import pyds, gi; gi.require_version('Gst', '1.0'); print('pyds OK')"

echo
echo "Colab setup complete. Start everything with:  bash scripts/run_all.sh"
