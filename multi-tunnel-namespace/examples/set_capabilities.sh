#!/usr/bin/env bash
# Grant the necessary capabilities to the Python interpreter in the venv.
# Run once (requires sudo).

set -euo pipefail

VENV_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.. && pwd)/.venv/bin/python"

if [ ! -f "$VENV_PY" ]; then
    echo "Error: venv Python not found at $VENV_PY"
    exit 1
fi

echo "Granting CAP_NET_ADMIN and CAP_SYS_ADMIN to: $VENV_PY"
sudo setcap cap_net_admin,cap_sys_admin+ep "$VENV_PY"

echo "Verifying:"
getcap "$VENV_PY"

echo "Done. You can now start the daemon as a normal user."
