#!/usr/bin/env bash
# Shared helpers: repo paths + environment variables from .env
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DS_ROOT="/opt/nvidia/deepstream/deepstream"

# Colab install (scripts/setup_colab.sh) keeps pyds + packages in a venv
if [[ -d /opt/ds-venv ]]; then
  export PATH="/opt/ds-venv/bin:$PATH"
fi

if [[ -f "$REPO_DIR/.env" ]]; then
  set -a; source "$REPO_DIR/.env"; set +a
else
  set -a; source "$REPO_DIR/.env.example"; set +a
fi
