#!/bin/bash
set -euo pipefail

usage() {
    printf 'usage: %s <runtime-prefix> <target> [fixture-dir]\n' "$0" >&2
    exit 2
}

[ $# -ge 2 ] && [ $# -le 3 ] || usage
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$1
target=$2
fixtures=${3:-$ROOT/.work/fixtures}
work=$ROOT/.work/tmp/qualify-runtime/$target
rm -rf "$work"
mkdir -p "$work"
export TMPDIR=$work

case $target in
    *-apple-darwin|*-linux-musl) ;;
    *) printf 'error: unsupported target %s\n' "$target" >&2; exit 2 ;;
esac
export PKG_CONFIG_LIBDIR=$prefix/lib/pkgconfig
unset PKG_CONFIG_PATH LD_LIBRARY_PATH DYLD_LIBRARY_PATH

TOOLS_WORK=$work/tools "$ROOT/tests/tools-workflows.sh" "$prefix" "$fixtures"

failed=0
check() {
    local name=$1
    shift
    if "$@" >"$work/last.log" 2>&1; then
        printf 'PASS runtime: %s\n' "$name"
    else
        printf 'FAIL runtime: %s\n' "$name"
        sed 's/^/    /' "$work/last.log" | tail -8
        failed=1
    fi
}

modules=(libavdevice libavformat libavcodec libavfilter libswscale libswresample libavutil)
check "pkg-config finds the runtime" pkg-config --exists "${modules[@]}"
check "headers are FFmpeg 9.0.2" grep -q '^#define FFMPEG_VERSION "9\.0\.2"$' "$prefix/include/libavutil/ffversion.h"

paths_in_prefix() {
    local flags resolved
    flags=$(pkg-config --cflags --libs "${modules[@]}")
    eval "set -- $flags"
    for flag in "$@"; do
        case $flag in
            -I*|-L*)
                resolved=$(cd "${flag#-?}" && pwd -P) || return 1
                case $resolved in
                    "$(cd "$prefix" && pwd -P)"/*) ;;
                    *) echo "outside: $flag"; return 1 ;;
                esac
                ;;
            -l*)
                case $flag in
                    -lavdevice|-lavformat|-lavcodec|-lavfilter|-lswscale|-lswresample|-lavutil) ;;
                    *) echo "unexpected library flag: $flag"; return 1 ;;
                esac
                ;;
        esac
    done
}
check "pkg-config resolves only the runtime prefix and libav* libraries" paths_in_prefix

link_consumer() {
    local flags
    flags=$(pkg-config --cflags --libs "${modules[@]}")
    eval "set -- $flags"
    cc -o "$work/runtime-consumer" "$ROOT/tests/sdk-consumer.c" "$@" "-Wl,-rpath,$prefix/lib"
}
check "external consumer links against the shared libraries" link_consumer
check "consumer decodes h264 and AV1 (libdav1d) through the shared libraries" \
    "$work/runtime-consumer" "$fixtures/video-h264.mp4" "$fixtures/video-av1.mp4" file pipe fd

runtime_closure() {
    case $target in
        *-apple-darwin)
            otool -L "$work/runtime-consumer" | tail -n +2 | awk '{ print $1 }' | while read -r library; do
                case $library in
                    @rpath/libav*.dylib|@rpath/libsw*.dylib|/usr/lib/*|/System/Library/Frameworks/*) ;;
                    *) echo "foreign: $library"; exit 1 ;;
                esac
            done
            ;;
        *)
            readelf -dW "$work/runtime-consumer" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | while read -r library; do
                case $library in
                    libav*.so.*|libsw*.so.*|libc.musl-*.so.1) ;;
                    *) echo "foreign: $library"; exit 1 ;;
                esac
            done
            ;;
    esac
}
check "consumer links only libav*, libsw*, and the system C library" runtime_closure

has_encoder() {
    "$prefix/bin/ffmpeg" -hide_banner -encoders | awk -v want="$1" '$2 == want { found = 1 } END { exit !found }'
}
case $target in
    *-apple-darwin)
        for encoder in hevc_videotoolbox aac_at mov_text; do
            check "encode needs encoder $encoder" has_encoder "$encoder"
        done
        ;;
esac

[ "$failed" -eq 0 ]
