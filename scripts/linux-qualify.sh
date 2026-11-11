#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/linux-container.sh"

[ $# -eq 1 ] || {
    printf 'usage: %s <dist/ffmpeg-...-linux-musl-<profile>.tar.gz>\n' "$0" >&2
    exit 2
}
archive=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
case $archive in
    "$ROOT"/*) relative=${archive#"$ROOT"/} ;;
    *) printf 'error: %s must be inside %s\n' "$archive" "$ROOT" >&2; exit 2 ;;
esac
name=$(basename "$archive")
case $name in
    *-x86_64-unknown-linux-musl-*) target=x86_64-unknown-linux-musl ;;
    *-aarch64-unknown-linux-musl-*) target=aarch64-unknown-linux-musl ;;
    *) printf 'error: %s is not a Linux musl archive\n' "$name" >&2; exit 2 ;;
esac
case $name in
    *-play-sdk.tar.gz|*-runtime.tar.gz) image=build ;;
    *-tools.tar.gz|*-fixtures.tar.gz) image=runtime ;;
    *) printf 'error: unknown profile in %s\n' "$name" >&2; exit 2 ;;
esac
platform=$(docker_platform_for "$target")

ensure_fixtures "$platform"
in_container "$platform" "$image" python3 build.py qualify --archive "$relative"
