# fixtures

`profiles/fixtures.json` is a test-only profile. It builds static `ffmpeg` and `ffprobe` for `x86_64-unknown-linux-musl` with the encoders Play's `tests/fixtures/gen.sh` needs: `libx264`, `libx265`, `libsvtav1`, `libvpx`, `libmp3lame`, and `libopus`, plus FFmpeg's native `aac`, `flac`, `alac`, `pcm_s16le`, `mpeg4`, `ffv1`, `mjpeg`, `png`, and subtitle encoders.

It is not a runtime. Releases carry it as one extra asset, `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz`, for generating test data only. The profile declares `"test_only": true`, `build.py` refuses any target that is not Linux, and the `tools` artifact means the stage holds only the two programs, with no headers or libraries a consumer could link. `runtime` and `tools` remain the shipped GPL profiles; `play-sdk` remains LGPL. The profile configures `--enable-gpl`, so the manifest license is `GPL version 2 or later`; x264 and x265 are GPLv2 and LAME is LGPL. The pair only generates test data.

The point is Play's Linux fixture gate: Play is moving its image off Alpine edge, and stable Alpine 3.24 ships FFmpeg 8.1.3, so the gate uses this pair to regenerate `tests/fixtures/manifest.json` and compare structure, dropping `sha256` and `bytes` the way `play/tests/harness.py` does.

## Commands

```sh
scripts/linux-build.sh x86_64-unknown-linux-musl fixtures
```

The script runs `build` and `audit` in the pinned `linux/amd64` Alpine image. The stage lands at `.work/stage/x86_64-unknown-linux-musl/fixtures/bin`. On an Apple Silicon host the container runs the `linux/amd64` image under emulation.

## Dependencies

| Source | Version | Build | Encoder |
| --- | --- | --- | --- |
| FFmpeg | 9.0.2 | `configure`, static-pie | programs |
| zlib | 1.3.2 | `configure --static` | `png` |
| x264 | `b35605a` | `configure --disable-cli --enable-static --disable-shared --enable-pic` | `libx264` |
| x265 | 4.3 | CMake, `ENABLE_SHARED=OFF`, `ENABLE_CLI=OFF`, 8-bit | `libx265` |
| SVT-AV1 | 4.2.0 | CMake, `BUILD_SHARED_LIBS=OFF`, `BUILD_APPS=OFF`, no LTO | `libsvtav1` |
| libvpx | 1.17.0 | `configure --target=x86_64-linux-gcc`, static, PIC | `libvpx-vp9` |
| LAME | 4.0 | `configure --disable-frontend --disable-decoder`, static, nasm | `libmp3lame` |
| Opus | 1.6.1 | `configure --disable-extra-programs`, static | `libopus` |

Every dependency is pinned by URL and SHA-256 in `sources.lock.json`, built with `-O2 -fPIC`, and installed into `.work/build/<target>/fixtures/deps`. libvpx embeds its configure arguments in the library, so it is configured with the neutral `/opt/ffmpeg-build` prefix, installed into the deps prefix through `DIST_DIR`, and its `vpx.pc` prefix is rewritten to the deps prefix. x265's CMake copies the shared-only `-lgcc_s` into `x265.pc`'s `Libs.private`, so the build drops it; a static link resolves those symbols from `-lgcc`.

libvpx 1.17.0 also needs GNU `diff` for its configure probe and Perl for `build/make/rtcd.pl`, which generates the runtime CPU-detection headers during `make`. The pinned `build` image has neither (`diff` is BusyBox and there is no `perl`), so the build image must add `diffutils` and `perl` before this profile can build.

x265 is built 8-bit (`HIGH_BIT_DEPTH=OFF`, the default). The fixture manifest records codec names and channel counts only, and `gen.sh` encodes HEVC with `-pix_fmt yuv420p`, so a 10-bit build would add nothing.

## Components

The profile requests the exact fixture generator inputs and outputs:

- Demuxers: `mov`, `matroska`, `avi`, `mp3`, `ogg`, `flac`, `wav`, `image2`, `concat`, `ffmetadata`, `webvtt`, `srt`, `ass`.
- Decoders: `png`, `mjpeg`, `subrip`, `ass`, `webvtt`.
- Encoders: the six external encoders above plus `aac`, `flac`, `alac`, `pcm_s16le`, `mjpeg`, `png`, `mpeg4`, `h263`, `ffv1`, `subrip`, `srt`, `mov_text`.
- Muxers: `mp4`, `mov`, `matroska`, `webm`, `avi`, `flac`, `mp3`, `wav`, `ogg`, `ipod`, `image2`.
- Filters: `testsrc2`, `sine`, `color`, `format`, `scale`, `aformat`, `aresample`, `null`, `anull`.
- Protocols: `file` only. Input devices: `lavfi` only.

`h263` is requested because the `mpeg4` encoder selects it. Configure auto-selects parsers, bitstream filters, and a few filters; `audit` requires every encoder and muxer to be requested, and no network protocols, devices, or `ffplay`.

## Using it

Put the stage's `bin` first on `PATH` (Play's generator calls plain `ffmpeg` and `ffprobe`, including `ffprobe` in its manifest step), then run Play's generator:

```sh
PATH="$PWD/.work/stage/x86_64-unknown-linux-musl/fixtures/bin:$PATH" \
    bash tests/fixtures/gen.sh .work/fixtures
```

The binaries are `-static-pie`, stripped, with a 2 MiB `PT_GNU_STACK`: no `INTERP`, no `NEEDED`, and no `GLIBC_` symbol versions. On Linux, structure must match the tracked manifest; the bytes differ from the macOS encoders, and Play compares each entry minus `sha256` and `bytes`.
