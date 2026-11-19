from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from importlib import import_module
from pathlib import Path

from select_mutation_scopes import SCOPES, module_shape, scope_source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scope", choices=sorted(SCOPES))
    parser.add_argument("runner")
    parser.add_argument("buildlib_scripts", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.buildlib_scripts.resolve(strict=True)))
    gate = import_module("mutants_gate")

    members = SCOPES[args.scope]
    source = Path(scope_source(args.scope))
    module = f"{source.stem}."
    prefixes = tuple(f"{module}x_{name}__mutmut_" for name in sorted(members))
    pyproject = Path("pyproject.toml")
    also_copy = ["tests", "sources.lock.json", ".work/cache/sources"]
    tests = "tests/test_bootstrap.py"
    if args.scope == "bootstrap":
        subprocess.run([sys.executable, "-c", "import bootstrap"], check=True)
    else:
        also_copy.extend(("bootstrap.py", "profiles", ".github/scripts", "patches", "scripts", "Makefile"))
        tests = "tests/test_build.py"
    with pyproject.open("a", encoding="utf-8") as config:
        config.write(
            f"\n[tool.mutmut]\nsource_paths = {json.dumps([str(source)])}\n"
            f"also_copy = {json.dumps(also_copy)}\n"
            f"pytest_add_cli_args_test_selection = {json.dumps([tests])}\nuse_setproctitle = false\n"
        )
    subprocess.run(
        [sys.executable, "-m", "mutmut", "run", "--max-children", "1",
         *(f"{prefix}*" for prefix in prefixes)],
        check=True,
    )

    generated = Path("mutants") / source
    metadata = generated.with_suffix(".py.meta")
    spans = generated.with_suffix(".py.spans")
    root = Path.cwd().resolve(strict=True)
    for path in (source, generated, metadata, spans):
        if not path.is_file() or path.resolve() != root / path:
            raise ValueError(f"expected a regular file in the checkout: {path}")

    receipt = gate.load_json(Path(".github/mutation-scopes.json"))[args.scope]
    keys = set(gate.load_json(metadata)["exit_code_by_key"])
    selected = {name for name in keys if name.startswith(prefixes)}
    if len(selected) != receipt["total"]:
        raise ValueError(f"{args.scope}: found {len(selected)} mutations, expected {receipt['total']}")
    outcomes = gate.read_results(metadata, spans, module, keys - selected)
    _, functions = module_shape(source.read_bytes())
    scoped_source = Path(".work/tmp/scoped-source")
    scoped_source.write_text(json.dumps({name: functions[name] for name in members}, sort_keys=True), encoding="utf-8")
    qualified = gate.qualified_survivors(
        scoped_source, generated, spans, module,
        {"source_sha256": receipt["source_sha256"], "survivors": receipt["survivors"][args.runner]},
    )
    counts = Counter(outcomes[name] for name in selected)
    print(args.scope, args.runner, dict(sorted(counts.items())))
    failures = [
        f"{outcomes[name]}: {name}"
        for name in sorted(selected)
        if outcomes[name] != "killed" and not (outcomes[name] == "survived" and name in qualified)
    ]
    if failures:
        raise ValueError("unqualified mutation outcomes:\n" + "\n".join(failures))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
