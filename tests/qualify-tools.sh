#!/bin/bash
set -euo pipefail

usage() {
    printf 'usage: %s <tools-prefix> <target> [fixture-dir]\n' "$0" >&2
    exit 2
}

[ $# -ge 2 ] && [ $# -le 3 ] || usage
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$1
target=$2
fixtures=${3:-$ROOT/.work/fixtures}

TOOLS_WORK=$ROOT/.work/tmp/qualify-tools/$target "$ROOT/tests/tools-workflows.sh" "$prefix" "$fixtures"

case $target in
    *-apple-darwin)
        encoders=$("$prefix/bin/ffmpeg" -hide_banner -encoders)
        for encoder in hevc_videotoolbox aac_at mov_text; do
            printf '%s\n' "$encoders" | awk -v want="$encoder" '$2 == want { found = 1 } END { exit !found }' || {
                printf 'FAIL tools: encode needs encoder %s\n' "$encoder"
                exit 1
            }
            printf 'PASS tools: encoder %s available\n' "$encoder"
        done
        ;;
esac
