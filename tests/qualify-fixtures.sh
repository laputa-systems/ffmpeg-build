#!/bin/bash
set -euo pipefail

[ $# -eq 2 ] || {
    printf 'usage: %s <fixtures-prefix> <target>\n' "$0" >&2
    exit 2
}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$1
work=$ROOT/.work/tmp/qualify-fixtures/$2
rm -rf "$work"
mkdir -p "$work"

video=(-f lavfi -i "testsrc2=size=160x120:rate=12:duration=1")
audio=(-f lavfi -i "sine=frequency=440:sample_rate=48000:duration=1")
status=0
check() {
    local name=$1 codec=$2 output=$3
    shift 3
    if ! "$prefix/bin/ffmpeg" -hide_banner -loglevel error -y "$@" "$work/$output"; then
        printf 'FAIL fixtures: %s encode\n' "$name"
        status=1
        return
    fi
    found=$("$prefix/bin/ffprobe" -v error -show_entries stream=codec_name -of csv=p=0 "$work/$output" | head -1)
    if [ "$found" = "$codec" ]; then
        printf 'PASS fixtures: %s encodes %s\n' "$name" "$codec"
    else
        printf 'FAIL fixtures: %s produced %s, expected %s\n' "$name" "${found:-nothing}" "$codec"
        status=1
    fi
}

check libx264 h264 x264.mp4 "${video[@]}" -c:v libx264 -preset ultrafast -pix_fmt yuv420p
check libx265 hevc x265.mkv "${video[@]}" -c:v libx265 -preset ultrafast -pix_fmt yuv420p -x265-params log-level=none
check libsvtav1 av1 svtav1.webm "${video[@]}" -c:v libsvtav1 -preset 12 -pix_fmt yuv420p
check libvpx-vp9 vp9 vpx.webm "${video[@]}" -c:v libvpx-vp9 -deadline realtime -cpu-used 8 -pix_fmt yuv420p
check libmp3lame mp3 lame.mp3 "${audio[@]}" -c:a libmp3lame
check libopus opus opus.ogg "${audio[@]}" -c:a libopus
exit "$status"
