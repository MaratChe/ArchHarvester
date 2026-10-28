#!/usr/bin/env bash
# Git Bash entrypoint; paths are converted before passing them to PowerShell.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
args=()
while (($#)); do
    case "$1" in
        --port|--data-dir|--ca-bundle)
            option="$1"
            if (($# < 2)) || [[ -z "$2" ]]; then
                echo "Missing value for $option" >&2; exit 2
            fi
            case "$option" in
                --port) args+=(-Port "$2") ;;
                --data-dir) args+=(-DataDir "$(cygpath -aw "$2")") ;;
                --ca-bundle) args+=(-CaBundle "$(cygpath -aw "$2")") ;;
            esac
            shift 2 ;;
        --no-browser) args+=(-NoBrowser); shift ;;
        --help|-h)
            echo 'Usage: bash scripts/start.sh [--port 8765] [--data-dir PATH] [--ca-bundle PEM] [--no-browser]'
            exit 0 ;;
        *) echo "Unknown argument: $1 (see --help)" >&2; exit 2 ;;
    esac
done
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$script_dir/start.ps1")" "${args[@]}"
