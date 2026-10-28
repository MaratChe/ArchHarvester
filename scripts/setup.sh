#!/usr/bin/env bash
# Git Bash on Windows; reuse the maintained PowerShell installation workflow.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$script_dir/setup.ps1")" "$@"
