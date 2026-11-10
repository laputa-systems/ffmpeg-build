Prefix: FFB
Next: 2

### FFB-1 · P3 · tools and runtime cannot encode WebP thumbnails

- **Area:** Build
- **Where:** `profiles/tools.json:67` (encoders), `profiles/tools.json:75` (muxers), `profiles/runtime.json:67`, `profiles/runtime.json:75`, `sources.lock.json:4`, `tests/tools-workflows.sh:145`
- **Problem:** Discover's public-site thumbnails (`~/d/discover/src/site/thumbnails.ts`) run `ffmpeg -v error -nostdin -y -i <png|jpeg|webp> -frames:v 1 -vf "scale=w='min(N,iw)':h='min(N,ih)':force_original_aspect_ratio=decrease" -map_metadata -1 -c:v libwebp -quality 78 -f webp <out>`. With the installed `runtime` build on PATH (`~/.local/bin/ffmpeg`, 9.0.2), that command fails with `Unrecognized option 'quality'`, because the profile has no `libwebp` encoder and no `webp` muxer. Discover's thumbnail and site-build tests fail as a result. Its input side is already covered: the `image2` demuxer, the `png`, `mjpeg`, and `webp` decoders, and the `scale` filter. Discover no longer needs the lavfi `color` source.
- **Recommendation:** Pin libwebp in `sources.lock.json` with its URL and SHA-256. Build it static and link it in. Add the `libwebp` encoder and the `webp` muxer to `tools`, and through the union rule to `runtime`. Add a `tests/tools-workflows.sh` check that runs the command above on a PNG and asserts a WebP comes out, and update the audit's expected component lists and `docs/tools-profile.md`. libwebp is BSD-licensed, so the GPL profiles are unaffected.
- **Fix with:** none
- **Effort:** S
