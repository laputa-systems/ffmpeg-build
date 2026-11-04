#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

usage() {
    printf 'usage: %s <x86_64-unknown-linux-musl|aarch64-unknown-linux-musl> <profile>\n' "$0" >&2
    exit 2
}

[ $# -eq 2 ] || usage
target=$1
profile=$2
case "$target" in
    x86_64-unknown-linux-musl) docker_platform=linux/amd64 ;;
    aarch64-unknown-linux-musl) docker_platform=linux/arm64 ;;
    *) usage ;;
esac

image="ffmpeg-build-${docker_platform#linux/}"
mkdir -p "$ROOT/.work/home" "$ROOT/.work/tmp"
docker build --platform "$docker_platform" --target build -q -t "$image" \
    -f "$ROOT/docker/Dockerfile" "$ROOT/docker" >/dev/null

docker run --rm --init --platform "$docker_platform" \
    --user "$(id -u):$(id -g)" \
    -e HOME=/work/.work/home \
    -e TMPDIR=/work/.work/tmp \
    -e GIT_CONFIG_COUNT=1 \
    -e GIT_CONFIG_KEY_0=safe.directory \
    -e GIT_CONFIG_VALUE_0=/work \
    -v "$ROOT:/work" -w /work \
    "$image" \
    sh -c 'python3 build.py build --target "$1" --profile "$2" && python3 build.py audit --target "$1" --profile "$2"' \
    sh "$target" "$profile"
