#!/bin/bash

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

docker_platform_for() {
    case "$1" in
        x86_64-unknown-linux-musl) printf 'linux/amd64\n' ;;
        aarch64-unknown-linux-musl) printf 'linux/arm64\n' ;;
        *) printf 'error: unsupported Linux target %s\n' "$1" >&2; return 2 ;;
    esac
}

container_image() {
    local platform=$1 stage=$2 tag
    tag="ffmpeg-build-$stage-${platform#linux/}"
    docker build --platform "$platform" --target "$stage" -q -t "$tag" \
        -f "$ROOT/docker/Dockerfile" "$ROOT/docker" >/dev/null || return
    printf '%s\n' "$tag"
}

in_container() {
    local platform=$1 stage=$2 image
    shift 2
    image=$(container_image "$platform" "$stage") || return
    mkdir -p "$ROOT/.work/home" "$ROOT/.work/tmp"
    local common git_mounts=()
    common=$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir) || return
    case "$common" in
        "$ROOT"/*) ;;
        *) git_mounts=(-v "$common:$common:ro") ;;
    esac
    docker run --rm --init --platform "$platform" \
        --user "$(id -u):$(id -g)" \
        -e HOME=/work/.work/home \
        -e TMPDIR=/work/.work/tmp \
        -e GIT_CONFIG_COUNT=1 \
        -e GIT_CONFIG_KEY_0=safe.directory \
        -e GIT_CONFIG_VALUE_0=/work \
        -v "$ROOT:/work" ${git_mounts[@]+"${git_mounts[@]}"} -w /work \
        "$image" "$@"
}

ensure_fixtures() {
    [ -s "$ROOT/.work/fixtures/movie-movtext.mp4" ] && return 0
    local platform=$1 target bindir
    case "$platform" in
        linux/amd64) target=x86_64-unknown-linux-musl ;;
        linux/arm64) target=aarch64-unknown-linux-musl ;;
        *) printf 'error: unsupported platform %s\n' "$platform" >&2; return 2 ;;
    esac
    "$ROOT/scripts/linux-build.sh" "$target" fixtures
    bindir="/work/.work/stage/$target/fixtures/bin"
    in_container "$platform" fixtures sh -c \
        'FIXTURE_FFMPEG="$1/ffmpeg" PATH="$1:$PATH" exec tests/fixtures/gen.sh .work/fixtures' \
        sh "$bindir"
}
