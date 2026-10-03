#!/bin/sh
# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
set -eu
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "Python 3 is required." >&2; exit 1
fi
exec "$PY" "$(dirname "$0")/bootstrap.py"
