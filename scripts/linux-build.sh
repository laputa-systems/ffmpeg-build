#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/linux-container.sh"

usage() {
    printf 'usage: %s <x86_64-unknown-linux-musl|aarch64-unknown-linux-musl> <play-sdk|tools>\n' "$0" >&2
    exit 2
}

[ $# -eq 2 ] || usage
target=$1
profile=$2
platform=$(docker_platform_for "$target") || usage
case "$profile" in
    play-sdk|tools) ;;
    *) usage ;;
esac

in_container "$platform" build sh -c \
    'python3 build.py build --target "$1" --profile "$2" && python3 build.py audit --target "$1" --profile "$2"' \
    sh "$target" "$profile"

[ "$profile" = tools ] || exit 0

ensure_fixtures "$platform"
clean=$ROOT/.work/tmp/clean-$target
rm -rf "$clean"
mkdir -p "$clean/prefix" "$clean/scratch"
cp -R "$ROOT/.work/stage/$target/tools/." "$clean/prefix/"

docker run --rm --init --platform "$platform" \
    --user "$(id -u):$(id -g)" \
    -e TOOLS_WORK=/scratch/run \
    -v "$clean/prefix:/opt/ffmpeg:ro" \
    -v "$ROOT/.work/fixtures:/fixtures:ro" \
    -v "$ROOT/tests:/tests:ro" \
    -v "$clean/scratch:/scratch" \
    -w /scratch \
    "$(container_image "$platform" runtime)" \
    sh -c 'test ! -e /work && uname -m && file -b /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe && /tests/tools-workflows.sh /opt/ffmpeg /fixtures'
