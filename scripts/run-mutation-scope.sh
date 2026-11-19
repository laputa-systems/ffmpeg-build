#!/usr/bin/env bash
set -euo pipefail

root="$PWD"
mkdir -p .work/tmp
proof=$(mktemp -d "$root/.work/tmp/whole-change.XXXXXXXX")
mkdir -p "$proof/.work/cache/sources" "$proof/.work/tmp"
touch "$proof/.work/cache/sources/.keep"
export TMPDIR="$proof/.work/tmp" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
git archive HEAD | tar -x -C "$proof"
uv run --frozen --python 3.15.2 --with mutmut==3.8.1 --with pytest==9.2.0 bash -euc '
  cd "$1"
  python .github/scripts/verify_mutation_scope.py "$2" "$3" "$4"
' whole-change "$proof" "$1" "$2" "$3"
