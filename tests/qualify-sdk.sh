#!/bin/bash
set -euo pipefail

usage() {
    printf 'usage: %s <sdk-prefix> <target> [fixture-dir]\n' "$0" >&2
    exit 2
}

[ $# -ge 2 ] && [ $# -le 3 ] || usage
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$1
target=$2
fixtures=${3:-$ROOT/.work/fixtures}
work=$ROOT/.work/tmp/qualify-sdk/$target
rm -rf "$work"
mkdir -p "$work"
export TMPDIR=$work

pkgconfig=$prefix/lib/pkgconfig
case $target in
    *-apple-darwin) export PKG_CONFIG_LIBDIR=$pkgconfig ;;
    *-linux-musl) export PKG_CONFIG_LIBDIR=$pkgconfig:/usr/lib/pkgconfig:/usr/share/pkgconfig ;;
    *) printf 'error: unsupported target %s\n' "$target" >&2; exit 2 ;;
esac
unset PKG_CONFIG_PATH

failed=0
check() {
    local name=$1
    shift
    if "$@" >"$work/last.log" 2>&1; then
        printf 'PASS sdk: %s\n' "$name"
    else
        printf 'FAIL sdk: %s\n' "$name"
        sed 's/^/    /' "$work/last.log" | tail -8
        failed=1
    fi
}

modules=(libavformat libavcodec libavfilter libswscale libswresample libavutil)
check "pkg-config finds the SDK" pkg-config --exists "${modules[@]}"
check "headers are FFmpeg 9.0.2" grep -q '^#define FFMPEG_VERSION "9\.0\.2"$' "$prefix/include/libavutil/ffversion.h"

paths_in_prefix() {
    local flags resolved
    flags=$(pkg-config --static --cflags --libs "${modules[@]}")
    eval "set -- $flags"
    for flag in "$@"; do
        case $flag in
            -I*|-L*)
                resolved=$(cd "${flag#-?}" && pwd -P) || return 1
                case $resolved in
                    "$(cd "$prefix" && pwd -P)"/*) ;;
                    /usr/include|/usr/lib) [ "${target#*-linux-}" != "$target" ] || { echo "outside: $flag"; return 1; } ;;
                    *) echo "outside: $flag"; return 1 ;;
                esac
                ;;
        esac
    done
}
check "pkg-config paths resolve inside the prefix" paths_in_prefix

link_consumer() {
    local flags
    flags=$(pkg-config --static --cflags --libs "${modules[@]}")
    eval "set -- $flags"
    cc -o "$work/sdk-consumer" "$ROOT/tests/sdk-consumer.c" "$@"
}
check "external consumer links with pkg-config --static" link_consumer
check "consumer decodes h264 and AV1 (libdav1d)" "$work/sdk-consumer" "$fixtures/video-h264.mp4" "$fixtures/video-av1.mp4"

system_only() {
    case $target in
        *-apple-darwin)
            otool -L "$work/sdk-consumer" | tail -n +2 | awk '{ print $1 }' | while read -r library; do
                case $library in
                    /usr/lib/*|/System/Library/Frameworks/*) ;;
                    *) echo "foreign: $library"; exit 1 ;;
                esac
            done
            ;;
        *)
            readelf -dW "$work/sdk-consumer" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | while read -r library; do
                case $library in
                    libc.musl-*.so.1|libva.so.2|libva-drm.so.2|libatomic.so.1) ;;
                    *) echo "foreign: $library"; exit 1 ;;
                esac
            done
            ;;
    esac
}
check "consumer links only system libraries" system_only

[ "$failed" -eq 0 ]
