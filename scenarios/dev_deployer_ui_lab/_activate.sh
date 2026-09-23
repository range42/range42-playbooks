#!/bin/bash

# deprecation algo issue with paramiko and ubuntu 24.04.2 LTS
# https://github.com/paramiko/paramiko/issues/2419

set -euo pipefail

VIRTUAL_ENV_DIR="$HOME/ansible_fix/venv"

if [ ! -d "$VIRTUAL_ENV_DIR" ]; then

    mkdir -p "$HOME/ansible_fix"
    python3 -m venv "$VIRTUAL_ENV_DIR"

    # shellcheck disable=SC1091
    source "$VIRTUAL_ENV_DIR/bin/activate"

    pip install --upgrade pip setuptools wheel
    pip install ansible paramiko cryptography
    # deactivate
fi

# shellcheck disable=SC1091
source "$VIRTUAL_ENV_DIR/bin/activate"

echo "source \"$VIRTUAL_ENV_DIR/bin/activate\""
