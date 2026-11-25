# fixtures

`profiles/fixtures.json` is a test-only profile. It builds static `ffmpeg` and `ffprobe` for `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl` with everything `tests/fixtures/gen.sh` needs: the external encoders `libx264`, `libx265`, `libsvtav1`, `libvpx` (VP8 and VP9), `libaom-av1`, `libmp3lame`, `libopus`, `libwebp`, `libvorbis`, and `libtheora`, the native encoders `aac`, `flac`, `alac`, `pcm_s16le`, `mjpeg`, `png`, `mpeg4`, `h263`, `ffv1`, `wmv2`, `wmav2`, `flv`, `mpeg2video`, `mp2`, `ac3`, `rv20`, `ass`, `subrip`, `srt`, `mov_text`, and `webvtt`, and the muxers, demuxers, decoders, parsers, bitstream filters, and filters the generator and `ffprobe` use on the files it writes.

It is not a runtime. Releases carry it as one extra asset, `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz`, for generating test data only. The profile declares `"test_only": true`, `build.py` refuses any target that is not Linux, and the `tools` artifact means the stage holds only the two programs, with no headers or libraries a consumer could link. `runtime` and `tools` remain the shipped GPL profiles; `play-sdk` remains LGPL. The profile configures `--enable-gpl`, so the manifest license is `GPL version 2 or later`; x264 and x265 are GPLv2 and LAME is LGPL. The pair only generates and inspects test data.

The point is the fixture gate: `scripts/linux-fixtures.sh` builds this profile in the pinned build image and runs `tests/fixtures/gen.sh` with `FIXTURE_FFMPEG` and `PATH` pointing at the stage, so fixtures come from this repository's own FFmpeg 9.0.2 build instead of a packaged FFmpeg whose version drifted (Alpine edge moved to FFmpeg 9.1). Play uses the same generator and `ffprobe` manifest step, so the profile also covers the demuxers, decoders, and subtitle components those fixtures need when probed.

## Commands

```sh
scripts/linux-build.sh x86_64-unknown-linux-musl fixtures
scripts/linux-build.sh aarch64-unknown-linux-musl fixtures
```

`scripts/linux-fixtures.sh` does both steps: it builds and audits the `fixtures` profile for the host's Linux target inside the pinned `build` image, then runs `tests/fixtures/gen.sh` inside the `fixtures` image with `FIXTURE_FFMPEG` and `PATH` set to the stage's `bin`. The stage lands at `.work/stage/<target>/fixtures/bin`. On an Apple Silicon host the `linux/arm64` image runs natively; the `linux/amd64` image runs under emulation.

## Dependencies

| Source | Version | Build | Encoder |
| --- | --- | --- | --- |
| FFmpeg | 9.0.2 | `configure`, static-pie | programs |
| zlib | 1.3.2 | `configure --static` | `png` |
| x264 | `b35605a` | `configure --disable-cli --enable-static --disable-shared --enable-pic` | `libx264` |
| x265 | 4.3 | CMake, `ENABLE_SHARED=OFF`, `ENABLE_CLI=OFF`, 8-bit | `libx265` |
| SVT-AV1 | 4.2.0 | CMake, `BUILD_SHARED_LIBS=OFF`, `BUILD_APPS=OFF`, no LTO | `libsvtav1` |
| libvpx | 1.17.0 | `configure --target=<arch>-linux-gcc`, static, PIC | `libvpx`, `libvpx-vp9` |
| LAME | 4.0 | `configure --disable-frontend --disable-decoder`, static, nasm | `libmp3lame` |
| Opus | 1.6.1 | `configure --disable-extra-programs`, static | `libopus` |
| libaom | 3.15.3 | CMake, `BUILD_SHARED_LIBS=OFF`, apps/examples/tests off | `libaom-av1` |
| libwebp | 1.6.0 | `configure --disable-shared --enable-static`, static | `libwebp` |
| libogg | 1.3.6 | `configure --disable-shared --enable-static` | — |
| libvorbis | 1.3.7 | `configure --disable-shared --enable-static`, static | `libvorbis` |
| libtheora | 1.2.0 | `configure --disable-shared --enable-static --disable-asm --disable-examples`, static | `libtheora` |

Every dependency is pinned by URL and SHA-256 in `sources.lock.json`, built with `-O2 -fPIC`, and installed into `.work/build/<target>/fixtures/deps`. libvpx embeds its configure arguments in the library, so it is configured with the neutral `/opt/ffmpeg-build` prefix, installed into the deps prefix through `DIST_DIR`, and its `vpx.pc` prefix is rewritten to the deps prefix. x265's CMake copies the shared-only `-lgcc_s` into `x265.pc`'s `Libs.private`, so the build drops it; a static link resolves those symbols from `-lgcc`.

libvpx 1.17.0 also needs GNU `diff` for its configure probe and Perl for `build/make/rtcd.pl`, which generates the runtime CPU-detection headers during `make`. The pinned `build` image has neither (`diff` is BusyBox and there is no `perl`), so the build image must add `diffutils` and `perl` before this profile can build.

x265 is built 8-bit (`HIGH_BIT_DEPTH=OFF`, the default). The fixture manifest records codec names and channel counts only, and `gen.sh` encodes HEVC with `-pix_fmt yuv420p`, so a 10-bit build would add nothing.

## Components

The profile requests the exact fixture generator inputs and outputs:

- Demuxers: `mov`, `matroska`, `avi`, `mp3`, `ogg`, `flac`, `wav`, `image2`, `concat`, `ffmetadata`, `webvtt`, `srt`, `ass`, `mpegts`, `asf`, `flv`, `mpegps`, `rm`, `webp_anim`.
- Decoders: the subtitle and image decoders above plus `h264`, `hevc`, `vp8`, `vp9`, `av1`, `mpeg4`, `h263`, `mpeg2video`, `wmv2`, `flv`, `theora`, `rv20`, `aac`, `mp3float`, `opus`, `vorbis`, `ac3`, `mp2float`, `wmav2`, `webp`, `pcm_s16le`.
- Encoders: the ten external encoders above plus `aac`, `flac`, `alac`, `pcm_s16le`, `mjpeg`, `png`, `mpeg4`, `h263`, `ffv1`, `wmv2`, `wmav2`, `flv`, `mpeg2video`, `mp2`, `ac3`, `rv20`, `ass`, `subrip`, `srt`, `mov_text`, `webvtt`.
- Muxers: `mp4`, `mov`, `tgp` (the `3gp` muxer), `matroska`, `webm`, `avi`, `flac`, `mp3`, `wav`, `ogg`, `ogv`, `ipod`, `image2`, `webp`, `mpegts`, `asf`, `flv`, `mpeg1system` (`mpeg`), `mpeg2vob` (`vob`), `rm`, plus `adts` and `latm`, which `mpegts` selects.
- Filters: `testsrc2`, `sine`, `color`, `format`, `scale`, `aformat`, `aresample`, `null`, `anull`.
- Protocols: `file` only. Input devices: `lavfi` only.

`h263` is requested because the `mpeg4` encoder selects it, and `adts`/`latm` because `mpegts` selects them. Component names are FFmpeg's config names, so the libvpx VP8 encoder is `libvpx_vp8` (runtime name `libvpx`) and the `3gp`, `mpeg`, and `vob` muxers are `tgp`, `mpeg1system`, and `mpeg2vob`. Configure auto-selects parsers, bitstream filters, and a few filters; `audit` requires every encoder and muxer to be requested, and no network protocols, devices, or `ffplay`.

## Using it

Put the stage's `bin` first on `PATH` (Play's generator calls plain `ffmpeg` and `ffprobe`, including `ffprobe` in its manifest step), then run the generator:

```sh
PATH="$PWD/.work/stage/x86_64-unknown-linux-musl/fixtures/bin:$PATH" \
    bash tests/fixtures/gen.sh .work/fixtures
```

`scripts/linux-fixtures.sh` already does this inside the `fixtures` container with `FIXTURE_FFMPEG` set to the stage's `ffmpeg`. The binaries are `-static-pie`, stripped, with a 2 MiB `PT_GNU_STACK`: no `INTERP`, no `NEEDED`, and no `GLIBC_` symbol versions. On Linux, structure must match the tracked manifest; the bytes differ from the macOS encoders, and Play compares each entry minus `sha256` and `bytes`.
