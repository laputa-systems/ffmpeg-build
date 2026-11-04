#!/bin/bash
set -euo pipefail

usage() {
    printf 'usage: %s <output-dir>\n' "$0" >&2
    exit 2
}

[ $# -eq 1 ] || usage
out=$1
ffmpeg=${FIXTURE_FFMPEG:-ffmpeg}

version=$("$ffmpeg" -hide_banner -version | awk 'NR == 1 { print $3 }')
[ "$version" = 9.0.2 ] || {
    printf 'error: fixtures need a full host FFmpeg 9.0.2; %s reports %s\n' "$ffmpeg" "$version" >&2
    exit 1
}

mkdir -p "$out"
ff() { "$ffmpeg" -nostdin -hide_banner -loglevel error -y "$@"; }
video=(-f lavfi -t 2 -i testsrc2=size=640x360:rate=30)
tone=(-f lavfi -i sine=frequency=440:duration=2)

ff "${video[@]}" -c:v libx264 -pix_fmt yuv420p -an "$out/video-h264.mp4"
ff "${video[@]}" -c:v libvpx-vp9 -b:v 200k -an "$out/video-vp9.webm"
ff "${video[@]}" -c:v libaom-av1 -cpu-used 8 -an "$out/video-av1.mp4"
ff "${video[@]}" -c:v libx265 -tag:v hvc1 -an -x265-params log-level=none "$out/video-hevc.mp4"
ff "${tone[@]}" -c:a aac -b:a 96k "$out/audio-aac.m4a"
ff "${tone[@]}" -c:a libopus -b:a 64k "$out/audio-opus.webm"
ff "${tone[@]}" -c:a libmp3lame -b:a 96k "$out/audio.mp3"
ff -f lavfi -i testsrc2=size=320x180 -frames:v 1 -c:v libwebp "$out/thumb.webp"
ff -f lavfi -i testsrc2=size=320x180 -frames:v 1 "$out/thumb.jpg"
ff -f lavfi -i testsrc2=size=320x180 -frames:v 1 "$out/thumb.png"

cat >"$out/subs.vtt" <<'VTT'
WEBVTT

00:00:00.000 --> 00:00:01.000
hello

00:00:01.000 --> 00:00:02.000
world
VTT

cat >"$out/subs.srt" <<'SRT'
1
00:00:00,000 --> 00:00:01,000
hello

2
00:00:01,000 --> 00:00:02,000
world
SRT

ff "${video[@]}" "${tone[@]}" -i "$out/subs.srt" -map 0:v -map 1:a -map 2:s \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -c:s srt "$out/movie-srt.mkv"
ff "${video[@]}" "${tone[@]}" -i "$out/subs.srt" -map 0:v -map 1:a -map 2:s \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -c:s ass "$out/movie-ass.mkv"
ff "${video[@]}" "${tone[@]}" -map 0:v -map 1:a -c:v libx264 -pix_fmt yuv420p -c:a aac \
    -f mpegts "$out/stream.ts"

legacy() {
    local name=$1
    shift
    ff "${video[@]}" "${tone[@]}" -map 0:v -map 1:a "$@" "$out/$name"
}
legacy legacy.mp4 -c:v libx264 -pix_fmt yuv420p -c:a aac
legacy legacy.mov -c:v mpeg4 -c:a aac
legacy legacy.webm -c:v libvpx -b:v 300k -c:a libvorbis
legacy legacy.avi -c:v mpeg4 -c:a libmp3lame
legacy legacy.wmv -c:v wmv2 -c:a wmav2
legacy legacy.flv -c:v flv -c:a libmp3lame -ar 44100
legacy legacy.mpg -c:v mpeg2video -c:a mp2 -f mpeg
legacy legacy.vob -c:v mpeg2video -c:a ac3 -f vob
legacy legacy.m2ts -c:v libx264 -pix_fmt yuv420p -c:a ac3 -f mpegts
legacy legacy.ogv -c:v libtheora -c:a libvorbis
legacy legacy.rm -c:v rv20 -c:a ac3
ff -f lavfi -t 2 -i testsrc2=size=352x288:rate=15 "${tone[@]}" -map 0:v -map 1:a \
    -c:v h263 -c:a aac -ar 16000 -ac 1 "$out/legacy.3gp"

cat >"$out/metadata.ffmeta" <<'META'
;FFMETADATA1
title=Fixture
artist=Fixture Uploader

[CHAPTER]
TIMEBASE=1/1000
START=0
END=1000
title=One

[CHAPTER]
TIMEBASE=1/1000
START=1000
END=2000
title=Two
META
ff -i "$out/movie-srt.mkv" -map 0 -c copy -c:s mov_text "$out/movie-movtext.mp4"
