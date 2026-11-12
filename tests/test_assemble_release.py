import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assemble_release", ROOT / ".github" / "scripts" / "assemble_release.py")
assert spec is not None and spec.loader is not None
assemble_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_release)
sys.path.insert(0, str(ROOT))
import build

COMMIT = "c" * 40
LOCK = "a" * 64
VERSION = "9.0.2"


class AssembleReleaseTests(unittest.TestCase):
    def setUp(self):
        build.TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=build.TMP_ROOT)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "artifacts"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_assets(self, stems, commit=COMMIT, lock=LOCK):
        paths = []
        for index, stem in enumerate(stems):
            directory = self.source / str(index)
            directory.mkdir()
            archive = directory / f"{stem}.tar.xz"
            manifest = json.dumps({"producer": {"commit": commit}}).encode()
            build.write_deterministic_archive(archive, stem, {"share/ffmpeg-build/manifest.json": (manifest, False)})
            profile, _, target = stem.removeprefix("ffmpeg-").partition(f"-{VERSION}-")
            sidecar = directory / f"{stem}.manifest.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "product": f"ffmpeg-{profile}",
                        "version": VERSION,
                        "target": target,
                        "source_revision": commit,
                        "sources_lock_sha256": lock,
                    }
                )
            )
            paths.extend([archive, sidecar])
        return paths

    def test_ten_products_with_manifests_and_sorted_sums(self):
        stems = assemble_release.expected_stems(VERSION)
        self.assertEqual(len(stems), 10)
        self.assertIn("ffmpeg-fixtures-9.0.2-x86_64-unknown-linux-musl", stems)
        names = assemble_release.assemble(self.write_assets(stems), self.root / "release", VERSION, COMMIT, LOCK)
        self.assertEqual(len(names), 20)
        sums = (self.root / "release" / "SHA256SUMS").read_text().splitlines()
        self.assertEqual([line.split("  ")[1] for line in sums], sorted(names))
        digest, name = sums[0].split("  ")
        self.assertEqual(digest, hashlib.sha256((self.root / "release" / name).read_bytes()).hexdigest())

    def test_rejects_missing_asset(self):
        stems = assemble_release.expected_stems(VERSION)
        paths = self.write_assets(stems)
        with self.assertRaises(ValueError):
            assemble_release.assemble(paths[1:], self.root / "release", VERSION, COMMIT, LOCK)

    def test_rejects_archive_from_other_commit(self):
        stems = assemble_release.expected_stems(VERSION)
        with self.assertRaises(ValueError):
            assemble_release.assemble(
                self.write_assets(stems, "d" * 40), self.root / "release", VERSION, COMMIT, LOCK
            )

    def test_rejects_manifest_for_other_lock(self):
        stems = assemble_release.expected_stems(VERSION)
        with self.assertRaises(ValueError):
            assemble_release.assemble(
                self.write_assets(stems, lock="b" * 64), self.root / "release", VERSION, COMMIT, LOCK
            )

    def test_names_match_build_naming(self):
        for stem in assemble_release.expected_stems(VERSION):
            build.parse_archive_name(f"{stem}.tar.xz")


if __name__ == "__main__":
    unittest.main()
