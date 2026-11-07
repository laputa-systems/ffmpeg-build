#!/bin/bash
set -uo pipefail

usage() {
    printf 'usage: %s <tools-prefix> [fixture-dir]\n' "$0" >&2
    exit 2
}

[ $# -ge 1 ] && [ $# -le 2 ] || usage
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$(cd "$1" && pwd)
fixtures=$(cd "${2:-$ROOT/.work/fixtures}" && pwd)
ffmpeg=$prefix/bin/ffmpeg
ffprobe=$prefix/bin/ffprobe
work=${TOOLS_WORK:-$ROOT/.work/tmp/tools-workflows}
rm -rf "$work"
mkdir -p "$work/tmp"
work=$(cd "$work" && pwd)
export TMPDIR=$work/tmp
cd "$work" || exit 1

passed=0
failed=0
case_result() {
    if [ "$1" -eq 0 ]; then
        printf 'PASS workflow: %s\n' "$2"
        passed=$((passed + 1))
    else
        printf 'FAIL workflow: %s\n' "$2"
        [ -s "$work/last.log" ] && tail -5 "$work/last.log" | sed 's/^/    /'
        failed=$((failed + 1))
    fi
}

check() {
    local name=$1
    shift
    "$@" >"$work/last.log" 2>&1
    case_result $? "$name"
}

ff() { "$ffmpeg" -nostdin -y -loglevel repeat+info "$@"; }

streams() {
    "$ffprobe" -v error -show_entries stream=codec_type,codec_name,codec_tag_string:stream_disposition=attached_pic \
        -print_format json "$1"
}

expect_streams() {
    local file=$1
    shift
    streams "$file" | python3 -c '
import json, sys
streams = json.load(sys.stdin)["streams"]
found = [f"{s['"'"'codec_type'"'"']}:{s['"'"'codec_name'"'"']}" for s in streams]
missing = [want for want in sys.argv[1:] if want not in found]
if missing:
    sys.exit(f"missing {missing}; found {found}")
' "$@"
}

expect_tag() {
    local value
    value=$("$ffprobe" -v error -show_entries "format_tags=$2" -of default=nw=1:nk=1 "$1") || return
    [ "$value" = "$3" ]
}

expect_chapters() {
    [ "$("$ffprobe" -v error -show_chapters -of csv=p=0 "$1" | wc -l | tr -d ' ')" = "$2" ]
}

expect_attached_pic() {
    streams "$1" | python3 -c '
import json, sys
streams = json.load(sys.stdin)["streams"]
if not any(s.get("disposition", {}).get("attached_pic") == 1 for s in streams):
    sys.exit("no attached_pic stream")
'
}

expect_faststart() {
    python3 - "$1" <<'PY'
import struct, sys
data = open(sys.argv[1], "rb").read()
offset, order = 0, []
while offset + 8 <= len(data):
    size, kind = struct.unpack(">I4s", data[offset:offset + 8])
    if size == 1:
        size = struct.unpack(">Q", data[offset + 8:offset + 16])[0]
    order.append(kind.decode("latin-1"))
    if size == 0:
        break
    offset += size
if "moov" not in order or "mdat" not in order or order.index("moov") > order.index("mdat"):
    sys.exit(f"moov does not precede mdat: {order}")
PY
}

version_is() {
    local banner
    banner=$("$1" -hide_banner -version) || return
    case ${banner%%$'\n'*} in
        "$2 version 9.0.2 "*) ;;
        *) printf 'banner: %s\n' "${banner%%$'\n'*}"; return 1 ;;
    esac
}

check "ffmpeg reports 9.0.2" version_is "$ffmpeg" ffmpeg
check "ffprobe reports 9.0.2" version_is "$ffprobe" ffprobe
check "ffplay absent" test ! -e "$prefix/bin/ffplay"
check "buildconf disables network" sh -c '"$1" -hide_banner -buildconf | grep -q -- --disable-network' sh "$ffmpeg"
check "yt-dlp feature probe finds setts" sh -c '"$1" -hide_banner -bsfs | grep -qx setts' sh "$ffmpeg"

check "probe json" sh -c '"$1" -hide_banner -show_format -show_streams -print_format json "file:$2" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d[\"streams\"] and d[\"format\"][\"format_name\"]"' \
    sh "$ffprobe" "$fixtures/legacy.mp4"

merge() {
    local name=$1 video=$2 audio=$3 vcodec=$4 acodec=$5
    cp "$fixtures/$video" "$name.fv.${video##*.}"
    cp "$fixtures/$audio" "$name.fa.${audio##*.}"
    check "merge $name into mp4" ff -i "file:$name.fv.${video##*.}" -i "file:$name.fa.${audio##*.}" \
        -c copy -map 0:v:0 -map 1:a:0 -movflags +faststart "file:$name.temp.mp4"
    check "merged $name streams" expect_streams "$name.temp.mp4" "video:$vcodec" "audio:$acodec"
    mv "$name.temp.mp4" "$name.mp4"
}
merge h264 video-h264.mp4 audio-aac.m4a h264 aac
merge vp9 video-vp9.webm audio-opus.webm vp9 opus
merge av1 video-av1.mp4 audio-opus.webm av1 opus
merge hevc video-hevc.mp4 audio-aac.m4a hevc aac

cp "$fixtures/subs.vtt" "clip.orig.vtt"
check "convert subtitles vtt to srt" ff -i "file:clip.orig.vtt" -f srt -movflags +faststart "file:clip.orig.srt"
check "converted srt has cues" grep -q -- '-->' clip.orig.srt

cp "$fixtures/metadata.ffmeta" "h264.meta"
check "embed metadata and chapters" ff -i "file:h264.mp4" -i "file:h264.meta" -map 0 -dn -ignore_unknown -c copy \
    -map_metadata 1 -write_id3v1 1 -metadata "title=Fixture h264" -metadata date=20261104 \
    -metadata "description=fixture description" -metadata "synopsis=fixture description" \
    -metadata purl=file:///fixture -metadata comment=file:///fixture -metadata "artist=Fixture Uploader" \
    -movflags +faststart "file:h264.temp.mp4"
mv h264.temp.mp4 h264.mp4
check "metadata title written" expect_tag h264.mp4 title "Fixture h264"
check "chapters written" expect_chapters h264.mp4 2

cp "$fixtures/thumb.webp" "h264.webp"
check "convert webp thumbnail to png" ff -f image2 -pattern_type none -i "file:h264.webp" -update 1 \
    -movflags +faststart "file:h264.png"
check "embed png thumbnail" ff -i "file:h264.mp4" -i "file:h264.png" -map 0 -dn -ignore_unknown -c copy \
    -map 1 -disposition:2 attached_pic -movflags +faststart "file:h264.temp.mp4"
mv h264.temp.mp4 h264.mp4
check "png thumbnail is attached_pic" expect_attached_pic h264.mp4
check "metadata survives thumbnail embed" expect_tag h264.mp4 title "Fixture h264"
check "thumbnail embed keeps faststart" expect_faststart h264.mp4

cp "$fixtures/thumb.jpg" "vp9.jpg"
check "embed jpeg thumbnail" ff -i "file:vp9.mp4" -i "file:vp9.jpg" -map 0 -dn -ignore_unknown -c copy \
    -map 1 -disposition:2 attached_pic -movflags +faststart "file:vp9.temp.mp4"
mv vp9.temp.mp4 vp9.mp4
check "jpeg thumbnail is attached_pic" expect_attached_pic vp9.mp4

audio_metadata() {
    local name=$1 fixture=$2
    shift 2
    cp "$fixtures/$fixture" "audio.$name"
    check "audio metadata $name" ff -i "file:audio.$name" -map 0 -dn -ignore_unknown "$@" -write_id3v1 1 \
        -metadata "title=Audio $name" -metadata date=20261104 -movflags +faststart "file:audio.temp.$name"
    check "audio $name title written" expect_tag "audio.temp.$name" title "Audio $name"
}
audio_metadata m4a audio-aac.m4a -vn -acodec copy
audio_metadata webm audio-opus.webm -c copy
audio_metadata mp3 audio.mp3 -c copy

check "remux mkv with srt to mp4 mov_text" ff -i "file:$fixtures/movie-srt.mkv" -map 0 -c copy -c:s mov_text \
    -movflags +faststart "file:remux-srt.mp4"
check "remuxed srt streams" expect_streams remux-srt.mp4 video:h264 audio:aac subtitle:mov_text
check "remux mkv with ass to mp4 mov_text" ff -i "file:$fixtures/movie-ass.mkv" -map 0 -c copy -c:s mov_text \
    "file:remux-ass.mp4"
check "remuxed ass streams" expect_streams remux-ass.mp4 subtitle:mov_text
check "embed srt into mp4 as mov_text" ff -i "file:h264.mp4" -i "file:clip.orig.srt" -map 0 -dn -ignore_unknown \
    -c copy -c:s mov_text -map 1:0 -metadata:s:s:0 language=eng "file:subs.temp.mp4"
check "embedded subtitle stream" expect_streams subs.temp.mp4 subtitle:mov_text
check "fix up mpegts to mp4" ff -i "file:$fixtures/stream.ts" -map 0 -dn -ignore_unknown -c copy -f mp4 \
    -bsf:a aac_adtstoasc -movflags +faststart "file:stream.temp.mp4"
check "fixed up streams" expect_streams stream.temp.mp4 video:h264 audio:aac

decode_all() {
    "$ffprobe" -v error -count_frames -show_entries stream=codec_type,nb_read_frames -of csv=p=0 "$1" |
        python3 -c '
import sys
rows = [line.strip().split(",") for line in sys.stdin if line.strip()]
kinds = {row[0] for row in rows if len(row) > 1 and row[1].isdigit() and int(row[1]) > 0}
if not {"video", "audio"} <= kinds:
    sys.exit(f"decoded {rows}")
'
}
for fixture in "$fixtures"/legacy.* "$fixtures"/movie-srt.mkv "$fixtures"/video-hevc.mp4; do
    case $fixture in
        */video-hevc.mp4) check "decode $(basename "$fixture")" sh -c '"$1" -v error -count_frames -show_entries stream=nb_read_frames -of csv=p=0 "$2" | grep -qx "[1-9][0-9]*"' sh "$ffprobe" "$fixture" ;;
        *) check "decode $(basename "$fixture")" decode_all "$fixture" ;;
    esac
done
check "decode av1 with libdav1d" sh -c '"$1" -v error -c:v libdav1d -i "$2" -map 0:v -f image2 -update 1 -frames:v 1 frame.png && test -s frame.png' \
    sh "$ffmpeg" "$fixtures/video-av1.mp4"

printf 'TOTAL %d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
