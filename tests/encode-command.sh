#!/bin/bash
set -uo pipefail

usage() {
    printf 'usage: %s <tools-prefix> [fixture-dir]\n' "$0" >&2
    exit 2
}

[ $# -ge 1 ] && [ $# -le 2 ] || usage
[ "$(uname -s)" = Darwin ] || {
    printf 'error: encode uses VideoToolbox and AudioToolbox and runs only on macOS\n' >&2
    exit 1
}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
prefix=$(cd "$1" && pwd)
fixtures=$(cd "${2:-$ROOT/.work/fixtures}" && pwd)
ffmpeg=$prefix/bin/ffmpeg
ffprobe=$prefix/bin/ffprobe
work=$ROOT/.work/tmp/encode-command
rm -rf "$work"
mkdir -p "$work"
export TMPDIR=$ROOT/.work/tmp

passed=0
failed=0
check() {
    local name=$1
    shift
    if "$@" >"$work/last.log" 2>&1; then
        printf 'PASS encode: %s\n' "$name"
        passed=$((passed + 1))
    else
        printf 'FAIL encode: %s\n' "$name"
        tail -5 "$work/last.log" | sed 's/^/    /'
        failed=$((failed + 1))
    fi
}

has_encoder() {
    "$ffmpeg" -hide_banner -encoders | awk -v want="$1" '$2 == want { found = 1 } END { exit !found }'
}

archive_hevc_encode() {
    local src=$1 output=$2 cap=$3
    "$ffmpeg" -nostdin -hide_banner -loglevel error -i "$src" \
        -map "0:V:0" -map "0:a:0" -map "0:s?" \
        -c:v hevc_videotoolbox \
        -pix_fmt yuv420p \
        -colorspace bt709 \
        -color_primaries bt709 \
        -color_trc bt709 \
        -q:v 52 \
        -tag:v hvc1 \
        -vf "scale='if(gt(iw,ih),-2,min(iw,$cap))':'if(gt(iw,ih),min(ih,$cap),-2)'" \
        -fps_mode passthrough \
        -c:a aac_at \
        -ac 2 \
        -b:a 128k \
        -c:s mov_text \
        -map_metadata -1 \
        -map_chapters -1 \
        -movflags +faststart \
        "$output"
}

expect_output() {
    local output=$1 subtitles=$2
    "$ffprobe" -v error -show_entries stream=codec_type,codec_name,codec_tag_string -print_format json "$output" |
        python3 -c '
import json, sys
streams = json.load(sys.stdin)["streams"]
found = {(s["codec_type"], s["codec_name"], s.get("codec_tag_string")) for s in streams}
want = {("video", "hevc", "hvc1"), ("audio", "aac", "mp4a")}
if sys.argv[1] == "yes":
    want.add(("subtitle", "mov_text", "tx3g"))
missing = want - found
if missing:
    sys.exit(f"missing {sorted(missing)}; found {sorted(found)}")
' "$subtitles"
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
if order.index("moov") > order.index("mdat"):
    sys.exit(f"moov does not precede mdat: {order}")
PY
}

for encoder in hevc_videotoolbox aac_at mov_text; do
    check "encoder $encoder available" has_encoder "$encoder"
done

for input in movie-srt.mkv movie-ass.mkv movie-movtext.mp4 legacy.mp4 legacy.webm legacy.avi legacy.wmv; do
    subtitles=no
    case $input in movie-*) subtitles=yes ;; esac
    output="$work/${input%.*}-encoded-archive-720p-cq52.mp4"
    check "archive-720p-cq52 $input" archive_hevc_encode "$fixtures/$input" "$output" 720
    check "$input output is hvc1 HEVC + AAC$([ $subtitles = yes ] && printf ' + mov_text')" expect_output "$output" "$subtitles"
    check "$input output has faststart" expect_faststart "$output"
done

printf 'TOTAL %d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
