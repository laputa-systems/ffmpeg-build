# Buildlib adoption

ffmpeg-build already pins `laputa-buildlib` 0.2.0 and imports it through `bootstrap.py` for
source-lock reading, verified source acquisition, hashing, release workspaces, manifests,
checksums, and target mapping. This record covers BLD-3 for the Node/CMake/FFmpeg cohort: the
audit of the remaining local implementations, the vendored interpreter bootstrap, the code that
changed, and the plan's per-repository proof. Base revision:
`5d46fd52671c853f65069fd939612e2d728bb573`. The code change is
`0783e876f9aa4f1d981d587048f7a68c264c598d`; the cold capsules below ran from a clean clone of
that commit. Later commits to this file are documentation only.

## 1. Bound the change

Public entrypoints are unchanged: the Make targets `fetch`, `build`, `package`, `verify`, `lint`,
`test`, `coverage`, `mutants-diff`, `clean`, the `build.py` subcommands, compiler flags, and the
archive/manifest/`SHA256SUMS` formats. The new `setup` target is additive. The actual controller
entrypoint is now `Makefile:1` `PYTHON ?= sh bootstrap/buildlib-run --`; direct invocation is
`sh bootstrap/buildlib-run -- build.py ...`.

| Local implementation (base) | What it did | Change |
| --- | --- | --- |
| `Makefile:1` `PYTHON ?= python3` | Ran the controller on whatever `python3` the host shipped, below the declared `requires-python = ">=3.15"` on many hosts. | Defaults to the vendored `bootstrap/buildlib-run`, which provides a pinned CPython 3.15 and the pinned wheel. |
| `Makefile:45` `uv run --frozen python -m unittest ...` | Tied the test gate to a development `uv` checkout. | Runs through `$(PYTHON)`; `uv` is no longer needed for `make test`. |
| README direct steps | Told a newcomer to run `python3 build.py ...` and `python3 -m unittest ...`. | Uses the shim and links `docs/DEVELOPMENT.md`. |
| — (no setup path) | No idempotent way to install verified distribution packages, the pinned `uv`, and the locked development tools. | `make setup` / `scripts/setup-dev`, modeled on node-build's proven path. |

Interpreter path a fresh host takes (base): the README told a newcomer to run `python3 build.py`;
`bootstrap.py:58` then downloaded the lock's wheel with `urllib` and inserted it on `sys.path`.
That depends on the distribution providing a Python new enough for the controller, and on network
access at first import. The shim removes the host-interpreter dependency and verifies the
interpreter and wheel by size and SHA-256 before use.

### Audit of remaining local code

Checked against buildlib 0.2.0 (`30ad4a0a8b697031a008b1de3b5359fc5cf6f2fe`):

- Already on buildlib, unchanged: `locks.load_sources` (`build.py:195`),
  `locks.fetch_input` (`build.py:502`), `hashing.sha256_file` (`build.py:1140`, `1141`, `1804`,
  `1943`, `2083`, `2088`, `2142`; `assemble_release.py:97`), `release.archive_name`,
  `create_archive`, `build_manifest`, `write_manifest`, `write_sha256sums` and `ReleaseError`
  (`build.py:2068`-`2088`; `assemble_release.py:56`, `87`, `105`), `targets.TARGETS`,
  `targets.native_target`, `targets.UnsupportedTargetError` (`build.py:213`, `321`).
- `bootstrap.py:14` `_digest`, `bootstrap.py:18` `_wheel`: parses the `laputa-buildlib` entry out
  of `sources.lock.json`, verifies the cached wheel, and downloads it with `urllib`. Buildlib's
  shim owns the same operation for its own cache. It is **retained**, not dead: `_wheel` is
  imported by the mutation lane (`scripts/run-mutation-scope.sh:8`,
  `.github/workflows/whole-change-mutation-trial.yml:59`) to seed `.work/cache/sources`, and
  `verify_mutation_scope.py` imports `bootstrap` in the archived proof. Those callers and the
  pinned `.github/mutation-scopes.json` receipts are outside this slice's writable paths, and
  `AGENTS.md` declares this import path. The shim and `_wheel` pin the same wheel (enforced by
  `tests/test_bootstrap_shim.py::VendoredBootstrapPinTest`).
- `build.py:1733` `elf_dynamic`: parses `readelf -dW` for NEEDED, SONAME, RUNPATH, RPATH, and
  TEXTREL. Buildlib's `elf.dependencies`/`rpaths` merge RPATH and RUNPATH and expose neither
  SONAME nor TEXTREL, so the local policy would not survive an exact rewrite. Retained with its
  tests.
- `build.py:1557` `gnu_stack_size`: reads the PT_GNU_STACK size from `readelf -lW`. The dynamic
  parse above already shells `readelf`; replacing only this helper would not remove that
  dependency or a shared operation.
- `build.py:1755` `macho_load_commands`, `build.py:1781` `library_identity`,
  `build.py:1552` `macos_linked_libraries`: parse `otool -l`/`-L`. The local load-command set
  includes `LC_LAZY_LOAD_DYLIB` and excludes `LC_LOAD_UPWARD_DYLIB`; buildlib's
  `macho.dependencies` has the opposite set, plus install name and rpaths. The local set is the
  FFmpeg consumer's policy, so the semantics do not match exactly.
- `build.py:1539` `object_kind_problem` and `ELF_MACHINE` (`build.py:1149`): match `file(1)` text
  (`"x86-64"`, `"ARM aarch64"`), not buildlib's structural arch names. Retained.
- `build.py:517` `extract_source`: `tar -xf` plus the consumer's `archive_root` membership check.
  Buildlib has no extraction helper.
- `build.py:860` `build_fingerprint`: hashes a recipe dict with `hashlib`, not a file; buildlib's
  file-digest helpers do not apply.

Consumer policy that stays local and validated: source-lock extension fields (`filename`,
`archive_root`, `role`, `tag`, `commit`), profile component/licence/device policy
(`build.py:19`-`152`, `445`-`900`), `ALLOWED_NEEDED`/framework policy, archive membership, modes
and symlinks (`build.py:2099`-`2151`), release layout, and every audit case. Buildlib's
structural readers do not prove any of them. The new bootstrap files are the only addition:
`bootstrap/buildlib-run`, `bootstrap/python.lock`, `scripts/setup-dev`, and
`tests/test_bootstrap_shim.py`.

## 2. Pin and exercise the installed bytes

- `sources.lock.json` pins `laputa-buildlib` 0.2.0 at
  `sha256:aaee620f0478544b1d32075b44de48e69bbcbd8b974d5f599d037494d59f4b4a`, size 25193.
- `pyproject.toml` pins `laputa-buildlib==0.2.0`; `uv.lock` records the same wheel URL, hash, and
  version.
- `bootstrap/python.lock` (vendored) pins the same wheel URL and SHA-256.
- `tests/test_bootstrap_shim.py::VendoredBootstrapPinTest` fails if the bootstrap wheel line and
  the source-lock entry diverge.

Import provenance, from the lane commit:

```text
$ sh bootstrap/buildlib-run -- -c 'import sys; sys.path.insert(0,"."); import build, buildlib; print(buildlib.__file__)'
.../.work/cache/sources/laputa_buildlib-0.2.0-py3-none-any.whl/buildlib/__init__.py
$ sh bootstrap/buildlib-run -- -c 'import sys; sys.path.insert(0,"."); sys.path.insert(0,".github/scripts"); import assemble_release, buildlib; print(buildlib.__file__)'
.../.work/cache/sources/laputa_buildlib-0.2.0-py3-none-any.whl/buildlib/__init__.py
$ shasum -a 256 .work/cache/sources/laputa_buildlib-0.2.0-py3-none-any.whl
aaee620f0478544b1d32075b44de48e69bbcbd8b974d5f599d037494d59f4b4a
```

Both controllers import from the wheel's `buildlib/__init__.py`; `bootstrap.py:58` puts that
pinned wheel ahead of the shim's `PYTHONPATH` entry, so a local source tree or an owner
`PYTHONPATH` cannot mask it. The shim's own cache entry has the same digest and is reported by
`scripts/setup-dev` (`3.15.2 /root/.cache/laputa-buildlib/aaee620f.../buildlib.whl/buildlib/__init__.py`
on the uv branch, `3.15.1` on the python-build branch).

### Vendored bootstrap provenance

| File | Source | Digest (SHA-256) | Local differences |
| --- | --- | --- | --- |
| `bootstrap/buildlib-run` | buildlib `30ad4a0a8b697031a008b1de3b5359fc5cf6f2fe` (`bootstrap/buildlib-run`) | `e7f957ca6af0b151d25a9ff5bedb5deca0bfc86ba05ff3225a5405d56fa95957` | none |
| `bootstrap/python.lock` | buildlib `30ad4a0a8b697031a008b1de3b5359fc5cf6f2fe` (`bootstrap/python.lock`) | `cab50541ce8b2c2a6a41829f26aac19344532d239535f4d6795d80d5af933832` | none |

Both files are byte-identical to buildlib 0.2.0 (`cmp` clean). Repin both together with the
package pin and the `sources.lock.json` wheel entry. The shim's trust paths are unchanged from
buildlib: python-build archives verify by size and SHA-256 before extraction; the uv fallback's
managed Python is verified by uv's upstream metadata, a distinct trust path recorded here rather
than claimed equivalent.

## 3. Boundary tests

New `tests/test_bootstrap_shim.py` (5 tests, passed under the shim):

- `test_verified_archives_and_wheel_run_the_python_from_the_cache`: a fixture server provides a
  verified interpreter archive and wheel; the shim selects `python-build` and executes the cached
  interpreter.
- `test_injected_wrong_wheel_digest_fails_before_running_python`: a wrong wheel SHA-256 fails with
  `sha256 mismatch` and the interpreter never runs.
- `test_injected_wrong_archive_size_fails_before_extracting`: a wrong archive size fails with
  `archive size mismatch` before extraction.
- `test_truncated_download_fails_clearly`: a truncated archive fails with
  `archive size mismatch`.
- `test_vendored_bootstrap_pins_the_same_wheel_as_the_source_lock`: package, source-lock, and
  bootstrap identities agree.

Preserved stronger checks (unchanged): `tests/test_bootstrap.py` still covers malformed pins, cache
reuse, verified replacement, and failure cleanup for `bootstrap.py`; archive admission, safe
staging, source-cache integrity, release-layout membership/modes/symlinks, complete `SHA256SUMS`,
and the qualification checks keep their tests. No test was weakened or skipped.

## 4. Compare outcomes

No release or archive format changed. Archive bytes, manifest fields, `SHA256SUMS`, `.tar.xz`
creation, relocation, linkage and hardening checks are unchanged; only the interpreter
provisioning and the Makefile's test runner changed. `.github/workflows/release.yml` was not
edited: its `python3 build.py version`, `python3 -m unittest`, and
`python3 .github/scripts/assemble_release.py` steps behave as before, with the same import path
through `bootstrap.py`. This slice did not run a full FFmpeg artifact build (the acceptance covers
the controller gates and cold capsules); repeated packaging of identical pinned inputs is
unchanged because the release code was not touched.

## 5. Prove the environment

macOS arm64 (native, Apple Silicon), from the lane commit:

| Gate | Base `5d46fd5` | Lane `0783e876` |
| --- | --- | --- |
| `make lint` | exit 0, Ruff and ty clean | exit 0, Ruff and ty clean |
| `make test` | exit 0, 168 tests, 14.965 s | exit 0, 173 tests, 7.409 s |

No test fails on the lane that does not fail identically on the base (zero failures on both).
`TMPDIR=$PWD/.work/tmp` on the host. The interpreter-only `make lint` path still uses the locked
Ruff and ty through `uv`.

Cold capsules, native arm64, fresh container, clean clone of `0783e876` made inside the container
from a read-only mount of the worktree (the common Git directory mounted read-only at its host
path so the worktree's `.git` file resolves), then `sh scripts/setup-dev`, `make lint`,
`make test`:

| Capsule | Branch (selected) | Interpreter | setup | lint | test | status lines | cold total |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ubuntu:24.04` arm64 | uv fallback (musl 1.2.4 is below 1.2.5) | uv-managed CPython 3.15.2 | 0 | 0 | 0 (173 tests) | 0 | 46 s |
| `ubuntu:26.04` arm64 + distro `musl` | python-build (musl 1.2.5) | pinned musl CPython 3.15.1 | 0 | 0 | 0 (173 tests) | 0 | 26 s |

`git status --porcelain` was empty in both clones. The cold total includes the one prerequisite
installed before cloning (`git`), distribution package installation in setup, the pinned `uv`, the
locked development dependencies, and the verifier; it is capsule wall-clock operational cost, not
a benchmark. Full logs are outside the repository under `.work/tmp/capsules/` (scratch). The
host's `.work/tmp` convention was not applied inside the capsules; `TMPDIR` stayed at the
distribution default.

## 6. Benefit and cost

- Duplicate/unsupported path removed: the controller no longer requires the distribution's
  `python3` to satisfy `>=3.15` (`Makefile:1`, README, and `make test`), and there is a documented
  one-command setup instead of an undocumented dependency on `uv`. `make test` no longer needs
  `uv`.
- Shared operations actually used after the slice: the buildlib interpreter/wheel bootstrap, plus
  the pre-existing lock, verified acquisition, hashing, release, manifest, checksum, and target
  helpers. The retained `bootstrap.py` downloader is the one overlapping implementation this
  slice did not remove; removing it requires updating the mutation selector/receipts and
  `AGENTS.md`, all outside the writable scope (see the follow-up below).
- Correctness gain: every controller invocation gets a SHA-256-pinned interpreter and wheel; a
  host without Python 3.15, `uv`, or `pip` still runs the documented gates; archive size is checked
  before extraction.
- Cold bytes: the uv branch downloads the pinned uv twice (15.1 MiB in setup for tools, 15.1 MiB
  again in the shim) because setup and the shim provision independent tools; the shim's uv branch
  also installs a 30.3 MiB CPython. The python-build branch downloads one 8.03 MiB CPython and the
  25,193-byte wheel. Development tools add about 23 MiB of Ruff/ty wheels once.
- Warm cost: `sh bootstrap/buildlib-run -- -c pass` is ~1.9 s with a populated cache (it
  re-hashes the pinned wheel, no download); `make test` is 7.4 s warm. These are operational
  observations, not a performance gate; no producer benchmark was established before this slice.

## Follow-up (outside this slice)

- The hosted mutation selector (`.github/scripts/select_mutation_scopes.py`) classifies unknown
  paths and needs `bootstrap/` added to its configuration inputs; the same change should regenerate
  the affected receipts if `bootstrap.py` is later reduced to a locator. Both files are outside
  this slice's writable paths, so the hosted mutation workflow is unverified here. Local
  `make lint test` and the capsules do not depend on it.
- Removing `bootstrap.py`'s downloader also needs `AGENTS.md` and the mutation lane updated
  together, after which `bootstrap.py` can fail loudly instead of downloading.

## Repin procedure

1. Change `laputa-buildlib==X.Y.Z` in `pyproject.toml`, run `uv lock`.
2. Update the `laputa-buildlib` entry in `sources.lock.json` (URL, SHA-256, size).
3. Re-vendor `bootstrap/buildlib-run` and `bootstrap/python.lock` from the new buildlib tag and
   update the digests above. The wheel line must match step 2.
4. `make setup && make lint test`, then the cold capsules.
