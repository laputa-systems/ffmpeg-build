#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/linux-container.sh"

case "$(uname -m)" in
    x86_64) platform=linux/amd64 ;;
    arm64|aarch64) platform=linux/arm64 ;;
    *) printf 'error: unsupported host %s\n' "$(uname -m)" >&2; exit 2 ;;
esac
ensure_fixtures "$platform"
