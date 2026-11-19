from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path

SCOPES = {
    "artifacts": frozenset({
        "archive_member_problems", "extracted_library_problems", "package", "parse_stage_manifest", "qualify",
    }),
    "audit": frozenset({"audit"}),
    "bootstrap": frozenset({"_digest", "_wheel"}),
    "build": frozenset({"build"}),
    "collector": frozenset({"archive_commit", "assemble", "check_manifest", "expected_assets", "expected_stems", "main"}),
    "dispatch": frozenset({"main"}),
    "runtime": frozenset({"audit_runtime"}),
    "runtime-binary": frozenset({"audit_runtime_elf", "audit_runtime_macho"}),
    "sdk": frozenset({"audit_sdk"}),
    "tools": frozenset({"audit_tools"}),
}

CONFIGURATION = frozenset({
    ".gitattributes", ".gitignore", "Makefile", "pyproject.toml", "sources.lock.json", "uv.lock",
})
INPUT_DIRECTORIES = (".github/", "patches/", "profiles/", "scripts/", "tests/")



def scope_source(scope: str) -> str:
    return {
        "bootstrap": "bootstrap.py",
        "collector": ".github/scripts/assemble_release.py",
    }.get(scope, "build.py")


def module_shape(source: bytes) -> tuple[list[str], dict[str, str]]:
    layout: list[str] = []
    functions: dict[str, str] = {}
    for statement in ast.parse(source).body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name in functions:
                raise ValueError(f"duplicate build function: {statement.name}")
            layout.append(f"def {statement.name}")
            functions[statement.name] = ast.dump(statement)
        else:
            layout.append(ast.dump(statement))
    return layout, functions


def changed_scopes(path: str, before: bytes, after: bytes) -> set[str]:
    old_layout, old_functions = module_shape(before)
    new_layout, new_functions = module_shape(after)
    if old_layout != new_layout:
        raise ValueError(f"module-level {path} changes need mutation qualification")
    changed = {name for name in old_functions if old_functions[name] != new_functions[name]}
    eligible = {scope: names for scope, names in SCOPES.items() if scope_source(scope) == path}
    unqualified = changed - set().union(*eligible.values())
    if unqualified:
        raise ValueError(f"build functions need mutation qualification: {sorted(unqualified)}")
    return {scope for scope, members in eligible.items() if members & changed}


def select(changes: Mapping[str, str], sources: Mapping[str, tuple[bytes, bytes]]) -> list[str]:
    selected: set[str] = set()
    for path, status in changes.items():
        if status not in {"A", "D", "M"}:
            raise ValueError(f"unsupported change status {status}: {path}")
        if path in sources:
            selected.update(changed_scopes(path, *sources[path]))
        elif path in CONFIGURATION or path.startswith(INPUT_DIRECTORIES):
            selected.update(SCOPES)
        elif not path.endswith(".md"):
            raise ValueError(f"unclassified mutation input: {path}")
    return sorted(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("buildlib_scripts", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.buildlib_scripts.resolve(strict=True)))
    parse_changes = import_module("mutants_gate").parse_changes

    base = subprocess.check_output([
        "git", "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}",
    ], text=True).strip()
    common = subprocess.check_output(["git", "merge-base", base, "HEAD"], text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--name-status", "-M", "-z", common, "HEAD"])
    changes = parse_changes(diff)
    sources = {
        path: (
            subprocess.check_output(["git", "show", f"{common}:{path}"]),
            subprocess.check_output(["git", "show", f"HEAD:{path}"]),
        )
        for path in {scope_source(scope) for scope in SCOPES}
        if changes.get(path) == "M"
    }
    print(json.dumps(select(changes, sources)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
