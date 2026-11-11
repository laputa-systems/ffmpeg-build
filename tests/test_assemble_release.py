import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assemble_release", ROOT / ".github" / "scripts" / "assemble_release.py")
assemble_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_release)
sys.path.insert(0, str(ROOT))
import build  # noqa: E402


class AssembleReleaseTests(unittest.TestCase):
    def setUp(self):
        build.TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=build.TMP_ROOT)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "artifacts"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_assets(self, names, commit="c" * 40):
        paths = []
        for index, name in enumerate(names):
            path = self.source / str(index) / name
            path.parent.mkdir()
            manifest = json.dumps({"producer": {"commit": commit}}).encode()
            root = name.removesuffix(".tar.gz")
            build.write_deterministic_archive(path, root, {"share/ffmpeg-build/manifest.json": (manifest, False)})
            paths.append(path)
        return paths

    def test_ten_assets_with_sums_and_release_json(self):
        names = assemble_release.expected_assets("9.0.2", "20261104")
        self.assertEqual(len(names), 10)
        self.assertIn("ffmpeg-9.0.2+20261104-x86_64-unknown-linux-musl-fixtures.tar.gz", names)
        release = assemble_release.assemble(self.write_assets(names), self.root / "release", "9.0.2", "20261104", "c" * 40)
        self.assertEqual([asset["name"] for asset in release["assets"]], names)
        written = json.loads((self.root / "release" / "release.json").read_text())
        self.assertEqual(written["commit"], "c" * 40)
        sums = (self.root / "release" / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(sums), 11)
        self.assertTrue(sums[-1].endswith("  release.json"))

    def test_rejects_missing_or_wrong_tag(self):
        names = assemble_release.expected_assets("9.0.2", "20261104")
        names[0] = names[0].replace("20261104", "20261103")
        with self.assertRaises(ValueError):
            assemble_release.assemble(self.write_assets(names), self.root / "release", "9.0.2", "20261104", "c" * 40)

    def test_rejects_archive_from_other_commit(self):
        names = assemble_release.expected_assets("9.0.2", "20261104")
        with self.assertRaises(ValueError):
            assemble_release.assemble(self.write_assets(names, "d" * 40), self.root / "release", "9.0.2", "20261104", "c" * 40)

    def test_names_match_build_naming(self):
        for name in assemble_release.expected_assets("9.0.2", "20261104-r2"):
            build.parse_archive_name(name)


if __name__ == "__main__":
    unittest.main()
