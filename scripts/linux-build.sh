#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

usage() {
    printf 'usage: %s <x86_64-unknown-linux-musl|aarch64-unknown-linux-musl> <play-sdk|tools>\n' "$0" >&2
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
case "$profile" in
    play-sdk|tools) ;;
    *) usage ;;
esac

arch=${docker_platform#linux/}
mkdir -p "$ROOT/.work/home" "$ROOT/.work/tmp"

image() {
    docker build --platform "$docker_platform" --target "$1" -q -t "ffmpeg-build-$1-$arch" \
        -f "$ROOT/docker/Dockerfile" "$ROOT/docker" >/dev/null
    printf 'ffmpeg-build-%s-%s\n' "$1" "$arch"
}

container() {
    local name=$1
    shift
    docker run --rm --init --platform "$docker_platform" \
        --user "$(id -u):$(id -g)" \
        -e HOME=/work/.work/home \
        -e TMPDIR=/work/.work/tmp \
        -e GIT_CONFIG_COUNT=1 \
        -e GIT_CONFIG_KEY_0=safe.directory \
        -e GIT_CONFIG_VALUE_0=/work \
        -v "$ROOT:/work" -w /work \
        "$(image "$name")" "$@"
}

container build sh -c \
    'python3 build.py build --target "$1" --profile "$2" && python3 build.py audit --target "$1" --profile "$2"' \
    sh "$target" "$profile"

[ "$profile" = tools ] || exit 0

fixtures=$ROOT/.work/fixtures
if [ ! -s "$fixtures/movie-movtext.mp4" ]; then
    container fixtures tests/fixtures/gen.sh .work/fixtures
fi

clean=$ROOT/.work/tmp/clean-$target
rm -rf "$clean"
mkdir -p "$clean/prefix" "$clean/scratch"
cp -R "$ROOT/.work/stage/$target/tools/." "$clean/prefix/"

docker run --rm --init --platform "$docker_platform" \
    --user "$(id -u):$(id -g)" \
    -e TOOLS_WORK=/scratch/run \
    -v "$clean/prefix:/opt/ffmpeg:ro" \
    -v "$fixtures:/fixtures:ro" \
    -v "$ROOT/tests:/tests:ro" \
    -v "$clean/scratch:/scratch" \
    -w /scratch \
    "$(image runtime)" \
    sh -c 'test ! -e /work && uname -m && file -b /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe && /tests/tools-workflows.sh /opt/ffmpeg /fixtures'
