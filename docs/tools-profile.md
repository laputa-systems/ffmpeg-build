# tools

`profiles/tools.json` defines the headless `ffmpeg`/`ffprobe` pair that `usr` installs. It exists for local postprocessing: yt-dlp merges, metadata, subtitles and thumbnails, and the macOS `encode` command. FFmpeg is not a network client here; yt-dlp remains the downloader.

## Commands

```sh
tests/fixtures/gen.sh .work/fixtures
python3 build.py build --target aarch64-apple-darwin --profile tools
python3 build.py audit --target aarch64-apple-darwin --profile tools
tests/tools-workflows.sh .work/stage/aarch64-apple-darwin/tools
tests/encode-command.sh .work/stage/aarch64-apple-darwin/tools
```

Linux targets build natively in the pinned Alpine image:

```sh
scripts/linux-build.sh x86_64-unknown-linux-musl tools
scripts/linux-build.sh aarch64-unknown-linux-musl tools
```

For `tools`, the script runs `build` and `audit`, generates fixtures in the `fixtures` image if they are missing, then copies the stage out of the build tree. It runs `tests/tools-workflows.sh` in the `runtime` image, a clean Alpine with only `bash`, `file`, and `python3`. That container mounts the copied prefix read-only and has no `/work`, so the pair cannot reach the build prefix.

`tests/fixtures/gen.sh` needs a full host FFmpeg 9.0.2: Homebrew on macOS, or the Alpine `ffmpeg` package in the `fixtures` stage of `docker/Dockerfile`. That FFmpeg is only a test dependency. The `tools` profile is not expanded to generate fixtures.

The stage holds only `bin/ffmpeg`, `bin/ffprobe`, and `share/ffmpeg-build/manifest.json`. zlib and dav1d build into `.work/build/<target>/tools/deps` and link statically. The binaries are stripped, and on macOS ad-hoc signed.

## Where the component set comes from

The component set comes from running the real commands, not from a guess. yt-dlp ran offline with `--load-info-json` and `--enable-file-urls` against `file://` fixtures, using the `vdl` and `mdl` flags from `usr/dotfiles/base/.local/bin`. Its `-v` output gave the exact FFmpeg command lines, which `tests/tools-workflows.sh` repeats. Without mutagen or AtomicParsley, yt-dlp embeds thumbnails through FFmpeg; that is the path tested. The `encode` arguments are copied from `usr/dotfiles/base/.local/bin/encode` into `tests/encode-command.sh`.

Ablation kept the set minimal. Candidates that no workflow needed were removed and the build re-run. Removed this way: the `aac` demuxer; the `png`, `mjpeg`, `webp`, `h263`, `vp8`, `ac3`, `opus`, `vorbis`, `mpegvideo`, `mpeg4video`, `av1`, `vp9`, `hevc`, and `mpegaudio` parsers; the `ass` demuxer; the `ssa` decoder; the native `av1` decoder (libdav1d decodes AV1); and the `null`, `anull`, `format`, and `aformat` filters. Those filters, plus the `ac3`, `mpegaudio`, and `vp9` parsers, come back as dependencies of other components and are listed under auto-selected. Each component that remains failed a workflow when it was absent, or is a direct requirement of one:

| Category | Requested | Workflow |
| --- | --- | --- |
| protocols | `file`, `pipe`, `fd` | every command; `pipe` and `fd` for stdin/stdout use |
| demuxers | `mov`, `matroska`, `mpegts`, `mp3`, `ogg` | yt-dlp merge, metadata and fixup inputs; `encode` mp4/mov/3gp/mkv/webm/ts/ogv inputs |
| | `avi`, `asf`, `flv`, `mpegps`, `mpegvideo`, `rm` | `encode` inputs `.avi`, `.wmv`/`.asf`, `.flv`, `.mpg`/`.vob`, `.rm`; MPEG-PS identifies video streams by probing with `mpegvideo` |
| | `image2` | thumbnail convert and embed |
| | `webvtt`, `srt`, `ffmetadata` | `--convert-subs srt`, subtitle embed, `--embed-metadata` chapters |
| decoders | `h264`, `hevc`, `vp8`, `vp9`, `libdav1d`, `mpeg4`, `h263`, `mpeg2video`, `wmv2`, `flv`, `theora`, `rv20` | `encode` video decode per input container |
| | `aac`, `mp3float`, `opus`, `vorbis`, `ac3`, `mp2float`, `wmav2` | `encode` audio decode per input container |
| | `png`, `mjpeg`, `webp` | thumbnail convert (`webp`); thumbnail embed needs dimensions (`png`, `mjpeg`) |
| | `subrip`, `ass`, `webvtt`, `mov_text` | subtitle convert, remux to `mov_text`, `encode` `-c:s mov_text` from mkv/mp4 |
| encoders | `png` | yt-dlp `ThumbnailsConvertor` |
| | `subrip` | `--convert-subs srt` |
| | `mov_text` | remux/embed into mp4; `encode` |
| | `hevc_videotoolbox`, `aac_at` (macOS only) | `encode` |
| muxers | `mp4`, `ipod`, `mov` | merge, metadata, thumbnail, fixup, `encode`; `mp4` and `ipod` depend on `mov` |
| | `webm`, `mp3` | `mdl` metadata on webm and mp3 audio |
| | `srt`, `image2` | subtitle and thumbnail convert |
| parsers | `h264`, `aac` | mpegts fixup to mp4 |
| bsfs | `aac_adtstoasc` | mpegts fixup to mp4 |
| | `setts` | yt-dlp probes `ffmpeg -bsfs` for `setts` and uses it in `FixupTimestamp` |
| filters | `scale`, `aresample` | `encode` `-vf scale`, `-ac 2` |

Auto-selected by configure and recorded in the manifest: `vp3` decoder (from `theora`), `vp9_superframe` and `vp9_superframe_split` bsfs, the `ac3`, `mpegaudio`, and `vp9` parsers, and the `aformat`, `anull`, `atrim`, `crop`, `format`, `hflip`, `null`, `rotate`, `transpose`, `trim`, and `vflip` filters. The `ffmpeg` program selects the filter graph defaults and autorotation.

`.m2v` is in `encode`'s extension list, but an elementary stream has no audio, and `encode` maps `0:a:0` unconditionally. It cannot succeed with any FFmpeg, so no fixture covers it.

## Restrictions

The audit enforces these. The profile uses `--disable-autodetect`, `--disable-everything`, `--disable-network`, and `--enable-gpl`. libavdevice is enabled only for the `lavfi` input device (`indevs` in the profile), which `-f lavfi` sources in the workflows and fixtures need; every other input and output device stays off. `cropdetect` requires GPL, so `tools` is GPL version 2 or later. Programs are `ffmpeg` and `ffprobe` only; `ffplay` is never built. There are no devices other than `lavfi`, no hwaccels or network protocols, and no encoder or muxer outside the requested set. dav1d is the only external library, and zlib and dav1d are linked statically. On macOS, `otool -L` lists only `/usr/lib/libSystem.B.dylib` and the AudioToolbox, VideoToolbox, CoreFoundation, CoreMedia, CoreVideo, and CoreServices frameworks. No file in the stage contains the build root.

`encode` hardware execution is separate from encoder availability. `tests/encode-command.sh` runs the full `archive-720p-cq52` command on this host, which exercises VideoToolbox. Seeing `hevc_videotoolbox` in `-encoders` alone does not prove that hardware encoding works.

## macOS result

```text
audit: 47 passed, 0 failed
tools-workflows: 55 passed, 0 failed
encode-command: 24 passed, 0 failed (Apple Silicon, VideoToolbox executed)
ffmpeg 8,756,256 B, ffprobe 8,570,544 B (stripped, ad-hoc signed)
```

## Linux

Linux `tools` links with `-static-pie -Wl,-z,stack-size=2097152`. The result is a static-pie ELF with no `INTERP` and no `NEEDED`, and no `GLIBC_` symbol version anywhere. VA-API, VideoToolbox, and AudioToolbox are absent; the audit checks that `hevc_videotoolbox` and `aac_at` are not in `-encoders`.

musl's default thread stack is 128 KiB, and FFmpeg's threaded demux/mux path overflows it. Without the larger stack, the mpegts-to-mp4 fixup segfaulted on aarch64. musl takes the default thread stack size from `PT_GNU_STACK`, so the link flag fixes it. The audit fails if `PT_GNU_STACK` is not exactly 2 MiB.

```text
audit: 59 passed, 0 failed (both targets)
tools-workflows in clean Alpine: 55 passed, 0 failed (both targets)
x86_64:  ffmpeg 14,317,816 B, ffprobe 14,092,472 B (static-pie, stripped)
aarch64: ffmpeg 10,033,760 B, ffprobe  9,771,584 B (static-pie, stripped)
```

`encode` is macOS-only; Linux has no HEVC encoder.
