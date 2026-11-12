#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/linux-container.sh"

[ $# -eq 1 ] || {
    printf 'usage: %s <dist/ffmpeg-<profile>-<version>-<linux-musl-target>.tar.xz>\n' "$0" >&2
    exit 2
}
archive=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
case $archive in
    "$ROOT"/*) relative=${archive#"$ROOT"/} ;;
    *) printf 'error: %s must be inside %s\n' "$archive" "$ROOT" >&2; exit 2 ;;
esac
name=$(basename "$archive")
case $name in
    *-x86_64-unknown-linux-musl.tar.xz) target=x86_64-unknown-linux-musl ;;
    *-aarch64-unknown-linux-musl.tar.xz) target=aarch64-unknown-linux-musl ;;
    *) printf 'error: %s is not a Linux musl archive\n' "$name" >&2; exit 2 ;;
esac
case $name in
    ffmpeg-play-sdk-*|ffmpeg-runtime-*) image=build ;;
    ffmpeg-tools-*|ffmpeg-fixtures-*) image=runtime ;;
    *) printf 'error: unknown profile in %s\n' "$name" >&2; exit 2 ;;
esac
platform=$(docker_platform_for "$target")

ensure_fixtures "$platform"
in_container "$platform" "$image" python3 build.py qualify --archive "$relative"
