# play-sdk

`profiles/play-sdk.json` is the authoritative playback profile. S1 builds its macOS `aarch64-apple-darwin` target; S2 adds the Linux targets.

## Commands

```sh
python3 build.py fetch --target aarch64-apple-darwin --profile play-sdk
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
```

`fetch` verifies every cached archive and every fresh download against `sources.lock.json`. `build` implies `fetch`, extracts into `.work/build/<target>/<profile>/src`, builds zlib and dav1d into the stage, writes `VERSION` into the FFmpeg tree before configure, and installs FFmpeg into `.work/stage/<target>/<profile>`.

A build is skipped only when the stamp fingerprint and the complete stage both match. The stamp records the source lock, profile, `build.py`, target, profile, configure flags, and toolchain.

## Components

The profile starts from the verified Player allowlist (`play/scripts/ffmpeg-components.txt` at `3bf9b42`). macOS requests:

- Demuxers: `mov`, `matroska`, `avi`, `mp3`, `flac`, `wav`, `ogg`.
- Decoders: `h264`, `hevc`, `libdav1d`, `vp9`, `mpeg4`, `png`, `mjpeg`.
- Parsers: `h264`, `hevc`, `av1`, `vp9`, `mpeg4video`, `aac`, `mpegaudio`, `opus`, `vorbis`, `flac`.
- Bitstream filters: `h264_mp4toannexb`, `hevc_mp4toannexb`, `vp9_superframe`, `aac_adtstoasc`, `extract_extradata`, `null`.
- Filters: `format`, `scale`, `aresample`, `aformat`, `fps`, `setpts`, `crop`, `transpose`, `hflip`, `vflip`, `hwdownload`, `hwupload`, `trim`, `atrim`, `concat`, `volume`, `pan`, `channelsplit`, `null`, `anull`.
- Hardware acceleration: `h264_videotoolbox`, `hevc_videotoolbox`.
- Protocols: `file`.

The PNG and JPEG decoders keep the album-art paths. VideoToolbox stays on macOS; the Linux profile will add the VA-API hwaccels and the native `av1` decoder they require. Subtitle decoders stay off because Player reads SubRip itself.

## Layout

The stage is an SDK prefix:

```text
include/                       FFmpeg, dav1d, and zlib headers
lib/*.a                        libav*.a, libdav1d.a, libz.a
lib/pkgconfig/*.pc             relocatable pkg-config files
share/ffmpeg-build/manifest.json
```

`share/man` and the FFmpeg example programs are removed after install; they are not part of the SDK. Licenses and the README arrive with packaging.

Every `.pc` file uses `prefix=${pcfiledir}/../..`, so the prefix can move without rewriting metadata. The FFmpeg `.pc` files carry the static dav1d and zlib link flags and the VideoToolbox/Core* frameworks.

## Manifest

`share/ffmpeg-build/manifest.json` records `contract`, `profile`, `target`, `sources`, `producer`, `configure_args`, the effective `configure` string, `components`, `requested_components`, `auto_selected`, `external_libraries`, `bundled_dependencies`, `frameworks`, and `toolchain` (`cc`, SDK, sysroot, deployment target, CPU baseline, host).

## S1 result

```text
ffversion: 9.0.2
programs: none
encoders: none
muxers: none
devices: none
protocols: file
external libraries: dav1d
bundled dependencies: dav1d, zlib
auto-selected: h263 (decoder), vp9_superframe_split (bsf)
audit: 47 passed, 0 failed
```

The build writes six static FFmpeg archives plus `libdav1d.a` and `libz.a`; all archive members are Mach-O arm64 objects, not LTO bitcode. `-fPIC` and `--enable-pic` are present. The toolchain is Apple clang 21.0.0 against the macOS 27.2 SDK with deployment target 27.0 and the default arm64 CPU baseline (no `-march=native`).
