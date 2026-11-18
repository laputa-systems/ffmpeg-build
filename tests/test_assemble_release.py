import hashlib
import importlib.util
import io
import json
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Literal
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assemble_release", ROOT / ".github" / "scripts" / "assemble_release.py")
assert spec is not None and spec.loader is not None
assemble_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_release)
sys.path.insert(0, str(ROOT))
import build
from bootstrap import release

COMMIT = "c" * 40
LOCK = "a" * 64
VERSION = "9.0.2"
ARCHIVE_MANIFEST = "asset/share/ffmpeg-build/manifest.json"


class AssembleReleaseTests(unittest.TestCase):
    def setUp(self):
        build.TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=build.TMP_ROOT)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "artifacts"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_assets(self, stems, archive_commit=COMMIT, lock=LOCK):
        paths = []
        for index, stem in enumerate(stems):
            directory = self.source / str(index)
            directory.mkdir()
            archive = directory / f"{stem}.tar.xz"
            manifest = json.dumps({"producer": {"commit": archive_commit}}).encode()
            tree = directory / "tree"
            (tree / "share" / "ffmpeg-build").mkdir(parents=True)
            (tree / "share" / "ffmpeg-build" / "manifest.json").write_bytes(manifest)
            release.create_archive(tree, archive, mtime=0, prefix=stem)
            shutil.rmtree(tree)
            profile, _, target = stem.removeprefix("ffmpeg-").partition(f"-{VERSION}-")
            sidecar = directory / f"{stem}.manifest.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "product": f"ffmpeg-{profile}",
                        "version": VERSION,
                        "target": target,
                        "source_revision": COMMIT,
                        "sources_lock_sha256": lock,
                    }
                )
            )
            paths.extend([archive, sidecar])
        return paths

    def invoke_command(self, *args: str | pathlib.Path) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = ["assemble_release.py", *map(str, args)]
        with patch.object(sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
            status: object = assemble_release.main()
        if type(status) is not int:
            self.fail(f"expected integer exit status, got {status!r}")
        return status, stdout.getvalue(), stderr.getvalue()

    def test_command_assembles_ten_products_with_manifests_and_sorted_sums(self):
        stems = assemble_release.expected_stems(VERSION)
        self.assertEqual(len(stems), 10)
        self.assertIn("ffmpeg-fixtures-9.0.2-x86_64-unknown-linux-musl", stems)
        lock = hashlib.sha256((ROOT / "sources.lock.json").read_bytes()).hexdigest()
        assets = self.write_assets(stems, lock=lock)
        destination = self.root / "new" / "release"
        status, stdout, stderr = self.invoke_command(self.source, destination, VERSION, COMMIT)
        self.assertEqual((status, stderr), (0, ""))
        names = stdout.splitlines()
        self.assertEqual(names, sorted(path.name for path in assets))
        sums = (destination / "SHA256SUMS").read_text().splitlines()
        self.assertEqual([line.split("  ")[1] for line in sums], names)
        digest = hashlib.sha256((destination / names[0]).read_bytes()).hexdigest()
        self.assertEqual(sums[0], f"{digest}  {names[0]}")

    def test_command_displays_usage_on_missing_arguments(self):
        status, stdout, stderr = self.invoke_command(self.source)
        self.assertEqual((status, stdout), (2, ""))
        self.assertEqual(stderr, "usage: assemble_release.py <artifacts-dir> <release-dir> <version> <commit>\n")

    def test_reports_missing_and_extra_assets(self):
        stems = assemble_release.expected_stems(VERSION)
        missing, *paths = self.write_assets(stems)
        unexpected = self.source / "unexpected.tar.xz"
        with self.assertRaises(ValueError) as error:
            assemble_release.assemble([*paths, unexpected], self.root / "release", VERSION, COMMIT, LOCK)
        self.assertEqual(
            str(error.exception),
            f"asset set mismatch: missing {[missing.name]}, unexpected {[unexpected.name]}",
        )

    def test_reports_duplicate_asset_name(self):
        paths = self.write_assets(assemble_release.expected_stems(VERSION))
        with self.assertRaises(ValueError) as error:
            assemble_release.assemble([*paths, paths[0]], self.root / "release", VERSION, COMMIT, LOCK)
        self.assertEqual(str(error.exception), f"duplicate asset {paths[0].name}")

    def test_rejects_archive_from_other_commit(self):
        stems = assemble_release.expected_stems(VERSION)
        wrong = "d" * 40
        with self.assertRaises(ValueError) as error:
            assemble_release.assemble(self.write_assets(stems, wrong), self.root / "release", VERSION, COMMIT, LOCK)
        self.assertEqual(str(error.exception), f"{stems[0]}.tar.xz was built from {wrong!r}, not {COMMIT}")

    def test_command_reports_manifest_for_other_lock(self):
        stems = assemble_release.expected_stems(VERSION)
        wrong = "b" * 64
        self.write_assets(stems, lock=wrong)
        lock = hashlib.sha256((ROOT / "sources.lock.json").read_bytes()).hexdigest()
        destination = self.root / "release"
        status, stdout, stderr = self.invoke_command(self.source, destination, VERSION, COMMIT)
        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(
            stderr,
            f"assemble failed: {stems[0]}.manifest.json: sources_lock_sha256 is {wrong!r}, expected {lock!r}\n",
        )
        self.assertFalse(destination.exists())

    def test_leaves_existing_destination_intact(self):
        assets = self.write_assets(assemble_release.expected_stems(VERSION))
        destination = self.root / "release"
        destination.mkdir()
        sentinel = destination / "preexisting"
        sentinel.write_bytes(b"existing release")
        with self.assertRaises(FileExistsError):
            assemble_release.assemble(assets, destination, VERSION, COMMIT, LOCK)
        self.assertEqual(list(destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"existing release")

    def write_archive(
        self, member: tarfile.TarInfo | None, payload: bytes = b"", *, mode: Literal["w:xz", "w:gz"] = "w:xz"
    ) -> pathlib.Path:
        archive = self.root / "asset.tar.xz"
        with tarfile.open(archive, mode) as tar:
            if member is not None:
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
        return archive

    def test_archive_commit_rejects_invalid_manifest_fields(self):
        cases = (
            ([], TypeError, "invalid archive manifest"),
            ({"producer": []}, TypeError, "invalid producer"),
            ({"producer": {"commit": 42}}, ValueError, "invalid commit"),
        )
        for manifest, error, message in cases:
            with self.subTest(manifest=manifest):
                archive = self.write_archive(tarfile.TarInfo(ARCHIVE_MANIFEST), json.dumps(manifest).encode())
                with self.assertRaisesRegex(error, message):
                    assemble_release.archive_commit(archive)

    def test_archive_commit_returns_none_for_absent_commit(self):
        for manifest in ({}, {"producer": {}}, {"producer": {"commit": None}}):
            with self.subTest(manifest=manifest):
                archive = self.write_archive(tarfile.TarInfo(ARCHIVE_MANIFEST), json.dumps(manifest).encode())
                self.assertIsNone(assemble_release.archive_commit(archive))

    def test_archive_commit_identifies_missing_or_non_file_manifest(self):
        directory = tarfile.TarInfo(ARCHIVE_MANIFEST)
        directory.type = tarfile.DIRTYPE
        cases = (
            (None, f"has no {ARCHIVE_MANIFEST}"),
            (directory, f"{ARCHIVE_MANIFEST} is not a file"),
        )
        for member, message in cases:
            with self.subTest(member=member), self.assertRaisesRegex(ValueError, message):
                assemble_release.archive_commit(self.write_archive(member))

    def test_archive_commit_rejects_non_xz_compression(self):
        manifest = json.dumps({"producer": {"commit": COMMIT}}).encode()
        archive = self.write_archive(tarfile.TarInfo(ARCHIVE_MANIFEST), manifest, mode="w:gz")
        with self.assertRaises(tarfile.ReadError):
            assemble_release.archive_commit(archive)

    def test_names_match_build_naming(self):
        for stem in assemble_release.expected_stems(VERSION):
            build.parse_archive_name(f"{stem}.tar.xz")


if __name__ == "__main__":
    unittest.main()
