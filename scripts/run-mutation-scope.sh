#!/usr/bin/env bash
set -euo pipefail

root="$PWD"
mkdir -p .work/tmp
proof=$(mktemp -d "$root/.work/tmp/whole-change.XXXXXXXX")
mkdir -p "$proof/.work/cache/sources" "$proof/.work/tmp"
wheel=$(uv run --frozen --no-sync --python 3.15.2 python -c 'from bootstrap import _wheel; print(_wheel())')
cp "$wheel" "$proof/.work/cache/sources/"
export TMPDIR="$proof/.work/tmp" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
git archive HEAD | tar -x -C "$proof"
uv run --frozen --python 3.15.2 bash -euc '
  cd "$1"
  python .github/scripts/verify_mutation_scope.py "$2" "$3" "$4"
' whole-change "$proof" "$1" "$2" "$3"
