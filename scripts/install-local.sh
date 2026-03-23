#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chmod +x "$ROOT/bin/backupkit"
chmod +x "$ROOT/lib/common.sh"
chmod +x "$ROOT/lib/policy_parser.py"
echo "OK: permisos aplicados"
