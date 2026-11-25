# Development environment

ffmpeg-build runs its controller on a pinned Python 3.15 with the pinned
`laputa-buildlib` wheel, provisioned by the vendored
[buildlib bootstrap](https://github.com/laputa-systems/buildlib/blob/main/docs/bootstrap.md).
No distribution Python, `uv`, or `pip` is required on the build path; the shim
downloads and verifies the interpreter and the wheel by size and SHA-256.

```sh
sh bootstrap/buildlib-run -- build.py version
sh bootstrap/buildlib-run -- -c 'import sys, buildlib; print(sys.version, buildlib.__file__)'
```

Arguments after `--` go to Python. Verified hosts: Apple Silicon macOS 27+ and
Linux x86-64/arm64 with musl >= 1.2.5 (Alpine, Debian 13, Ubuntu 26.04 with the
`musl` package). On glibc hosts without a compatible musl loader (Ubuntu 24.04)
the shim uses a pinned `uv` binary and uv's upstream CPython, verified by uv's
metadata.

## One-command setup

```sh
make setup          # or: sh scripts/setup-dev
make lint test
```

`scripts/setup-dev` is idempotent. It installs the distribution packages below
on a verified Linux distribution, installs the pinned `uv` for development
tooling, syncs the locked development dependencies, and checks that the
bootstrap brings up Python and the wheel. It fails clearly on an unverified
distribution.

| Package (Linux) | Consumer |
| --- | --- |
| `curl`, `ca-certificates` | `buildlib-run` and `scripts/setup-dev` downloads |
| `tar`, `xz-utils` | archive extraction (`buildlib-run`, `setup-dev`) |
| `git` | release provenance, the controller tests |
| `make` | the documented `make` gates |
| `musl` (Ubuntu 26.04, Debian 13) | the python-build interpreter branch of `buildlib-run` |

On macOS, install the Xcode command line tools (`xcode-select --install`) for
the native toolchain; everything else comes from the bootstrap.

## Development tools

`make lint` runs Ruff and ty, pinned in `uv.lock` and installed by `make setup`.
They are development-only, not controller runtime dependencies. `make coverage`
assumes the same development environment. `make test` runs the controller tests
through the shim and needs no development-tool installation.

## Optional tools

- Docker with a working daemon runs the native Linux builds in the
  digest-pinned Alpine image used by CI (`scripts/linux-build.sh`,
  `scripts/linux-qualify.sh`); it is not needed for `make lint test`.
- `scripts/linux-fixtures.sh` generates the workflow fixtures
  (`tests/fixtures/gen.sh .work/fixtures`) with this repository's own
  `fixtures` profile build inside the pinned Linux container; a full host
  FFmpeg 9.0.2 also works.
- A native toolchain is required for `make build` on macOS and inside the Linux
  container; it is not needed for `make lint test`.

See [buildlib-adoption.md](buildlib-adoption.md) for how the bootstrap and
shared helpers were adopted, and [baseline.md](baseline.md) for the recorded
build evidence.
