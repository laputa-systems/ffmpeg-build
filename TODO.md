Prefix: FFB
Next: 10

### FFB-6 · P2 · tools lacks the filters, null muxer and libx265 that toolbox's movie and music commands run

- **Area:** Profiles / Consumers
- **Where:** profiles/tools.json; docs/tools-profile.md (component table)
- **Problem:** The usr-installed tools ffmpeg (~/.local/bin/ffmpeg -> release-ac29c7720327f7dee4ed4677ce8421673fcc3563-aarch64-apple-darwin-runtime, FFmpeg 9.0.2, repomod which: owned) is first on PATH, but joshuarli/toolbox (`uv run tool ...`) invokes FFmpeg components the profile does not build, because toolbox is not one of the profile's named workflows (only yt-dlp and usr's encode are). Checked with `ffmpeg -h filter=NAME` / `-h muxer=null` / `-h encoder=libx265`: missing filters loudnorm, ebur128, astats, asplit, firequalizer, zscale, tonemap; missing muxer null; missing encoder libx265. Reproduction: `ffmpeg -hide_banner -f lavfi -i sine=d=1 -af ebur128 -f null -` fails with `Error opening output file -.`. Toolbox call sites: `movies loudnorm` (src/tool/movies/loudnorm.py loudnorm filter, null muxer after toolbox PR #15), `movies encode` crop detection (src/tool/movies/crop.py `-f null`), post-encode decode check (src/tool/movies/encode.py:1184 `-f null -`), `--hdr-policy tonemap` (encode.py:407 zscale+tonemap), the libx265 preset (encode.py:656), `music` loudness (src/tool/music/loudness.py:54 ebur128 + null) and scan verdict (src/tool/music/verdict.py:91-118 asplit/firequalizer/astats + null). Those commands fail on this host and their toolbox tests skip, so toolbox works only when Homebrew's full FFmpeg (/opt/homebrew/bin, later on PATH) is moved ahead of it.
- **Recommendation:** Decide whether toolbox is a tools consumer. If yes: add the toolbox workflows to tests/tools-workflows.sh (loudnorm measurement, ebur128, the verdict astats graph, cropdetect to null, zscale/tonemap) and add the components that fail them: the null muxer and the loudnorm, ebur128, astats, asplit and firequalizer filters (all LGPL, internal); zscale needs libzimg and libx265 needs x265 (GPL, already in the profile's license), so add those only if the tonemap and libx265 workflows stay supported. Record them in the component table. If no: say in docs/tools-profile.md that the tools pair is not a general FFmpeg and toolbox must use a full FFmpeg. Accept: `ffmpeg -h filter=loudnorm`, `-h filter=ebur128`, `-h filter=astats` and `-h muxer=null` succeed on the installed tools pair, and toolbox's `uv run pytest tests/movies/test_loudnorm.py tests/music/test_loudness.py` pass with only that ffmpeg on PATH; or the docs state the non-consumer decision.
- **Fix with:** reference-parity
- **Effort:** M

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
- **Where:** docs/baseline.md; Makefile:30
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

### FFB-8 · P3 · Mutation-qualify the bundled libva and libdrm build steps

- **Area:** tests · mutation
- **Where:** build.py build_libdrm, build_libva, RUNTIME_VA_LIBRARIES; .github/scripts/select_mutation_scopes.py SCOPES
- **Problem:** FFB-7 (laputa-systems/ffmpeg-build#88) added module-level build functions and a constant, which the whole-change mutation trial refuses by design (`module-level build.py changes need mutation qualification`), so the new libva/libdrm build and bundling code merged with functional verification only (full x86_64 runtime build, 163 audit checks, 55 Alpine workflow checks, qualification, 150 unit tests, Ubuntu and Alpine runtime checks) and no mutation run.
- **Recommendation:** Add build_libdrm and build_libva to a mutation scope (with the receipts the selector expects), qualify RUNTIME_VA_LIBRARIES through the runtime audit scope, and run the scopes on both Linux architectures.
- **Fix with:** none
- **Effort:** M

### FFB-9 · P2 · The build scope's mutation receipt is stale, so every whole-change run fails

- **Area:** tests · mutation
- **Where:** .github/mutation-scopes.json `build` (total 336, source_sha256 dc8734d7…); scripts/run-mutation-scope.sh; build.py x_build
- **Problem:** build.py's build function grew (d16c33a4 bundled libva, 2d6770e9 self-built fixtures) without regenerating the receipt, so the native mutation jobs stop with `build: found 357 mutations, expected 336` on any change that selects the build scope, including fleet buildlib bumps that touch only pins (laputa-systems/ffmpeg-build#90, merged red).
- **Recommendation:** Rerun the build scope natively on ubuntu-26.04, ubuntu-26.04-arm and xcode-27, record the new total, source hash and per-runner survivors, and kill or justify new survivors; fold in FFB-8's libva/libdrm scope while the runners are warm.
- **Fix with:** none
- **Effort:** M
