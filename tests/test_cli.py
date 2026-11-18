import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "build.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


class ControllerCommandTests(unittest.TestCase):
    def test_version_prints_the_locked_release(self):
        lock = json.loads((ROOT / "sources.lock.json").read_text())
        expected = next(entry["version"] for entry in lock["inputs"] if entry["name"] == "ffmpeg")
        result = run_command("version")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, f"{expected}\n", ""))

    def test_audit_rejects_a_target_outside_the_profile(self):
        result = run_command("audit", "--target", "not-a-target", "--profile", "tools")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(result.stderr, "error: target not-a-target is not in profile tools\n")

    def test_package_requires_a_profile(self):
        result = run_command("package", "--target", "aarch64-apple-darwin")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(
            result.stderr.splitlines()[-1],
            "build.py package: error: the following arguments are required: --profile",
        )


class ControllerDispatchTests(unittest.TestCase):
    def test_dispatch_and_status(self):
        import build

        target = "aarch64-apple-darwin"
        profile = {"name": "fixture"}
        sources = {"source": "fixture"}
        cases = (("fetch", "fetch_profile_sources", 0), ("build", "build", 0),
                 ("audit", "audit", 17), ("package", "package", 0))
        actions = {operation for _, operation, _ in cases}
        for command, operation, expected in cases:
            argv = ["build.py", command, "--target", target, "--profile", "tools"]
            with (
                self.subTest(command=command),
                mock.patch.object(sys, "argv", argv),
                mock.patch.multiple(
                    build, load_profile=mock.DEFAULT, target_config=mock.DEFAULT,
                    load_sources=mock.DEFAULT, **dict.fromkeys(actions, mock.DEFAULT),
                ) as calls,
            ):
                calls["load_profile"].return_value = (profile, None)
                calls["load_sources"].return_value = sources
                calls["audit"].return_value = 17
                self.assertEqual(build.main(), expected)
                calls["load_profile"].assert_called_once_with("tools")
                calls["target_config"].assert_called_once_with(profile, target)
                args = (profile, sources) if command == "fetch" else (target, "tools")
                calls[operation].assert_called_once_with(*args)
                for unused in actions - {operation}:
                    calls[unused].assert_not_called()
                self.assertEqual(calls["load_sources"].call_count, int(command == "fetch"))

    def test_qualify_dispatches_path_and_returns_status(self):
        import build

        with mock.patch.object(sys, "argv", ["build.py", "qualify", "--archive", "some path/archive.tar.xz"]), mock.patch.object(build, "qualify", return_value=13) as qualify:
            self.assertEqual(build.main(), 13)
        qualify.assert_called_once_with(Path("some path/archive.tar.xz"))

    def test_parser_rejects_missing_and_unknown_arguments(self):
        for args in ((), ("unknown",), ("fetch", "--profile", "tools"), ("qualify",), ("version", "extra")):
            with self.subTest(args=args):
                result = run_command(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error:", result.stderr)

    def test_version_dispatch_prints_version(self):
        import build

        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["build.py", "version"]), mock.patch.object(build, "load_sources", return_value={"ffmpeg": SimpleNamespace(version="fixture-version")}), redirect_stdout(output):
            self.assertEqual(build.main(), 0)
        self.assertEqual(output.getvalue(), "fixture-version\n")

    def test_old_python_fails_before_parsing(self):
        import build

        with mock.patch.object(sys, "version_info", (3, 11, 9, "final", 0)), mock.patch.object(build.platform, "python_version", return_value="3.11.9"), mock.patch.object(build, "fail", side_effect=RuntimeError) as fail, self.assertRaises(RuntimeError):
            build.main()
        fail.assert_called_once_with("build.py needs Python 3.12 or newer for safe tar extraction; this is 3.11.9")

    def test_parser_errors_and_help_in_main(self):
        import build

        cases = ([], ["fetch", "--profile", "tools"], ["package", "--target", "t"], ["qualify"])
        for args in cases:
            with self.subTest(args=args), mock.patch.object(sys, "argv", ["build.py", *args]), redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit) as exit_status:
                build.main()
            self.assertEqual(exit_status.exception.code, 2)
            self.assertIn("required", error.getvalue())
        with mock.patch.object(sys, "argv", ["build.py", "--help"]), redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exit_status:
            build.main()
        self.assertEqual(exit_status.exception.code, 0)
        self.assertIn("Build, audit, and inspect the pinned FFmpeg profiles.", output.getvalue())

    def test_python_312_is_accepted(self):
        import build

        with mock.patch.object(sys, "version_info", (3, 12, 0, "final", 0)), mock.patch.object(sys, "argv", ["build.py", "version"]), mock.patch.object(build, "load_sources", return_value={"ffmpeg": mock.Mock(version="v")}), mock.patch("builtins.print"):
            self.assertEqual(build.main(), 0)
