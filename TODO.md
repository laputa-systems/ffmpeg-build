Prefix: FFB
Next: 3

### FFB-1 · P3 · tools and runtime cannot encode WebP thumbnails

- **Area:** Build
- **Where:** `profiles/tools.json:67` (encoders), `profiles/tools.json:75` (muxers), `profiles/runtime.json:67`, `profiles/runtime.json:75`, `sources.lock.json:4`, `tests/tools-workflows.sh:145`
- **Problem:** Discover's public-site thumbnails (`~/d/discover/src/site/thumbnails.ts`) run `ffmpeg -v error -nostdin -y -i <png|jpeg|webp> -frames:v 1 -vf "scale=w='min(N,iw)':h='min(N,ih)':force_original_aspect_ratio=decrease" -map_metadata -1 -c:v libwebp -quality 78 -f webp <out>`. With the installed `runtime` build on PATH (`~/.local/bin/ffmpeg`, 9.0.2), that command fails with `Unrecognized option 'quality'`, because the profile has no `libwebp` encoder and no `webp` muxer. Discover's thumbnail and site-build tests fail as a result. Its input side is already covered: the `image2` demuxer, the `png`, `mjpeg`, and `webp` decoders, and the `scale` filter. Discover no longer needs the lavfi `color` source.
- **Recommendation:** Pin libwebp in `sources.lock.json` with its URL and SHA-256. Build it static and link it in. Add the `libwebp` encoder and the `webp` muxer to `tools`, and through the union rule to `runtime`. Add a `tests/tools-workflows.sh` check that runs the command above on a PNG and asserts a WebP comes out, and update the audit's expected component lists and `docs/tools-profile.md`. libwebp is BSD-licensed, so the GPL profiles are unaffected.
- **Fix with:** none
- **Effort:** S

### FFB-2 · P3 · Releases cannot serve as Chromium's system FFmpeg, so the Hydrogen browser compiles its own

- **Area:** Profiles / Consumers
- **Where:** profiles/runtime.json; profiles/play-sdk.json; sources.lock.json (FFmpeg 9.0.2); laputa-systems/chromium-build config/inputs.lock (Chromium 156.0.8078.79, DEPS ffmpeg_revision 9db86ce5b5b454dfc96c435f9f0723012980c37f, chromium/third_party/ffmpeg reporting FFMPEG_VERSION git-2026-08-25-e5441fe421); chromium-build scripts/prepare-source.py (desktop line forces the bundled FFmpeg)
- **Problem:** chromium-build's Hydrogen desktop browser (ungoogled Chromium 156, musl, arm64 and amd64) compiles Chromium's bundled third_party/ffmpeg into the browser because no available system FFmpeg is new enough. Chromium tracks FFmpeg's development branch: 156's media/filters/ffmpeg_demuxer.cc needs AV_CODEC_ID_ITUT_T35, AV_STREAM_GROUP_PARAMS_TREF and AVDynamicHDRSmpte2094App5. The 9.0.2 runtime release has the last two but not AV_CODEC_ID_ITUT_T35, and Alpine's FFmpeg has none. So the browser carries a second FFmpeg with its own codec configuration and security-update cadence, separate from the one play and usr use.
- **Recommendation:** Add a Chromium-facing profile (or extend runtime) that tracks the FFmpeg revision a pinned Chromium release names in DEPS (chromium/third_party/ffmpeg), built shared for aarch64- and x86_64-unknown-linux-musl with the headers and pkg-config files Chromium's use_system_ffmpeg build reads, and limited to the decoders, demuxers and parsers Chromium's Chrome branding enables (media/ffmpeg/ffmpeg_common.cc and third_party/ffmpeg/chromium/config/Chrome/linux). Prove it by building chromium-build's chromium-wayland-release profile with system FFmpeg against the release, and record the codec list difference from Chromium's bundled config. chromium-build would then switch its desktop line to system FFmpeg and ship the libav*/libsw* closure in its runtime.
- **Fix with:** none
- **Effort:** L

