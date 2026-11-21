import io
import sys
import unittest
from contextlib import redirect_stderr
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github/scripts"))

selection = import_module("select_mutation_scopes")


class MutationSelectionTests(unittest.TestCase):
    def test_source_and_deleted_test_scopes_are_unioned(self):
        old = b"def audit_tools():\n    return 0\n"
        new = b"def audit_tools():\n    return 1\n"
        sources = {"build.py": (old, new)}

        with redirect_stderr(io.StringIO()) as log:
            self.assertEqual(selection.select({"build.py": "M"}, sources), ["tools"])
            self.assertEqual(selection.select({"build.py": "M", "tests/test_build.py": "D"}, sources), sorted(selection.SCOPES))
        self.assertIn("M build.py selects tools", log.getvalue())
        self.assertIn("D tests/test_build.py selects ", log.getvalue())

    def test_source_only_spelling_change_selects_its_known_scopes(self):
        old = b"def audit_tools():\n    return 0\n"
        new = b"def audit_tools():\n    return 0  # spelling\n"
        expected = sorted(scope for scope in selection.SCOPES if selection.scope_source(scope) == "build.py")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(selection.select({"build.py": "M"}, {"build.py": (old, new)}), expected)

    def test_documentation_paths_have_no_selected_scope(self):
        with redirect_stderr(io.StringIO()) as log:
            self.assertEqual(selection.select({"README.md": "M", "tests/README.md": "A"}, {}), [])
        self.assertEqual(log.getvalue().splitlines(), ["M README.md documentation", "A tests/README.md documentation"])

    def test_the_vendored_bootstrap_selects_every_scope(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(selection.select({"bootstrap/buildlib-run": "M"}, {}), sorted(selection.SCOPES))

    def test_unknown_functions_and_module_bindings_fail_selection(self):
        old = b"def unclassified():\n    return 0\n"
        with self.assertRaisesRegex(ValueError, "unclassified"):
            selection.select({"build.py": "M"}, {"build.py": (old, old.replace(b"0", b"1"))})
        with self.assertRaisesRegex(ValueError, "module-level build.py"):
            selection.select({"build.py": "M"}, {"build.py": (old, b"STATE = 1\n" + old)})
        with self.assertRaisesRegex(ValueError, "unclassified mutation input"):
            selection.select({"new.py": "A"}, {})
