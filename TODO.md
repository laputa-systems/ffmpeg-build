Prefix: FFB
Next: 6

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

### FFB-3 · P3 · Measure shipped media throughput

- **Area:** Runtime performance
- **Where:** tests/tools-workflows.sh:187; tests/encode-command.sh:45; tests/qualify-runtime.sh:78
- **Problem:** Unproven: qualification checks output but has no representative timed decode or encode workload, so a user-visible playback or transcoding slowdown could ship unseen. There is no paired baseline, resource attribution, or host-validity record.
- **Recommendation:** Establish target-specific shipped-profile decode and encode workloads with pinned media, completed-work and correctness checks, paired baselines, and separate CPU and memory attribution.
- **Fix with:** bench-pyramid
- **Effort:** L

### FFB-4 · P3 · Measure profile build cost

- **Area:** Build performance
- **Where:** plan.md:81; Makefile:30
- **Problem:** Historical profile build timings were taken on a busy host and include emulation for Linux; they do not establish repeatable native build time, CPU, memory or I/O baselines per target.
- **Recommendation:** Define repeatable clean and warm profile builds with input and host identity, completed artifacts, paired comparisons and separate process-tree resource attribution.
- **Fix with:** bench-pyramid
- **Effort:** M

### FFB-5 · P3 · Track shipped artifact size and startup

- **Area:** Artifact performance
- **Where:** docs/baseline.md:32; Makefile:36; tests/tools-workflows.sh:108
- **Problem:** The historical size figures describe Player, not current producer archives; qualification checks program version but does not measure shipped binary startup. Changes to size or startup have no producer baseline or regression check.
- **Recommendation:** Measure profile archive and installed sizes and target-specific ffmpeg and ffprobe startup against comparable artifacts; record the inputs and distinguish cold and warm startup.
- **Fix with:** bench-pyramid
- **Effort:** M

