#!/usr/bin/env bash
set -euo pipefail

if [[ -n $(git status --porcelain=v1) ]]; then
  printf '%s\n' 'Mutation selection requires a clean checkout of committed changes.' >&2
  exit 1
fi

case "$(uname -s):$(uname -m)" in
  Linux:x86_64) native_runner=ubuntu-26.04 ;;
  Linux:aarch64|Linux:arm64) native_runner=ubuntu-26.04-arm ;;
  Darwin:arm64) native_runner=xcode-27 ;;
  *) printf '%s\n' 'Mutation selection requires a supported native host.' >&2; exit 1 ;;
esac

mkdir -p .work/tmp
scratch=$(mktemp -d "$PWD/.work/tmp/mutation-buildlib.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
export TMPDIR="$PWD/.work/tmp"
git -C "$2" archive "$(< .github/mutation-buildlib-revision)" scripts/mutants_gate.py | tar -x -C "$scratch"
scopes=$(uv run --frozen --python 3.15.2 python .github/scripts/select_mutation_scopes.py --lines "$1" "$scratch/scripts")
if [[ -z $scopes ]]; then
  printf '%s\n' 'No changed mutation scopes.'
  exit 0
fi

while IFS= read -r scope; do
  scripts/run-mutation-scope.sh "$scope" "$native_runner" "$scratch/scripts"
done <<< "$scopes"
