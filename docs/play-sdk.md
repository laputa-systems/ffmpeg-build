# play-sdk

`profiles/play-sdk.json` is the authoritative playback profile. It has three targets: `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, and `aarch64-unknown-linux-musl`.

## Commands

```sh
python3 build.py fetch --target aarch64-apple-darwin --profile play-sdk
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
```

Linux targets build natively inside the pinned Alpine image in `docker/Dockerfile`; `build.py` refuses a target whose platform and architecture differ from the host's:

```sh
scripts/linux-build.sh x86_64-unknown-linux-musl play-sdk
scripts/linux-build.sh aarch64-unknown-linux-musl play-sdk
```

The script runs `build` and `audit` in a `linux/amd64` or `linux/arm64` container, with the repository mounted at `/work`. On Apple Silicon, arm64 runs natively and x86-64 runs under emulation. The build does not need a `play` checkout.

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

Linux adds the native `av1` decoder and the `h264_vaapi`, `hevc_vaapi`, `vp9_vaapi`, and `av1_vaapi` hwaccels, configured with `--enable-vaapi`.

The PNG and JPEG decoders keep the album-art paths. VideoToolbox stays on macOS and VA-API on Linux. Subtitle decoders stay off because Player reads SubRip itself.

## Platform flags

| Target | Flags | CPU baseline | Consumer links |
| --- | --- | --- | --- |
| `aarch64-apple-darwin` | `--enable-videotoolbox`, `-mmacosx-version-min=27.0` | arm64 default | VideoToolbox, CoreFoundation, CoreMedia, CoreVideo, CoreServices |
| `x86_64-unknown-linux-musl` | `--enable-vaapi`, `--arch=x86_64` | `-march=x86-64` | `libva`, `libva-drm` |
| `aarch64-unknown-linux-musl` | `--enable-vaapi`, `--arch=aarch64` | `-march=armv8-a` | `libva`, `libva-drm`, `libatomic` |

Every target uses `--enable-pic` and `-fPIC`. The SDK bundles no GPU driver or desktop stack: `libva` and `libva-drm` are system libraries that the consumer links. They appear in `libavutil.pc` as `-lva-drm -lva`, and the manifest lists them under `system_libraries`. GCC adds `-latomic` on aarch64 Linux.

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

`share/ffmpeg-build/manifest.json` records `contract`, `profile`, `target`, `sources`, `producer`, `configure_args`, the effective `configure` string, `components`, `requested_components`, `auto_selected`, `external_libraries`, `bundled_dependencies`, `frameworks`, `system_libraries`, and `toolchain` (`cc`, SDK, sysroot, deployment target, CPU baseline, host, and on Linux the musl version).

## Audit result

macOS:

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

Linux (both targets):

```text
ffversion: 9.0.2
programs: none
encoders, muxers, devices: none
protocols: file
ELF machine: x86-64 / ARM aarch64 for every archive member
CPU flags: -march=x86-64 / -march=armv8-a; no -march=native, no x86 flag on aarch64
glibc: no GLIBC_ symbol version in any archive
toolchain: Alpine GCC 15.2.0, musl 1.2.6, sysroot /
pkg-config: libavutil.pc declares -lva-drm -lva
audit: 55 passed, 0 failed
```

ABI note: these are static archives for musl, which has no symbol versioning. The only runtime ABI the consumer takes on is that of the system `libva` and `libva-drm`.
