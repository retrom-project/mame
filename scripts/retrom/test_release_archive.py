import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from release_archive import build_archive


class ReleaseArchiveTest(unittest.TestCase):
    def test_raw_only_repeatable_archive_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            candidate.mkdir()
            payloads = {"LICENSES.txt": b"MAME license", "mame-common.wasm": b"\0asm" * 100,
                        "mame-apple.wasm": b"\0asm" * 10}
            entries = []
            for name, data in sorted(payloads.items()):
                (candidate / name).write_bytes(data)
                entries.append({"filename": name, "sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            (candidate / "retrom-core-candidate.json").write_text(json.dumps({
                "kind": "RETROM_CORE_CANDIDATE_V1", "coreId": "mame",
                "repository": "https://github.com/retrom-project/mame", "adapterAbi": "retrom-mame-dylink-v1",
                "dirty": False, "files": entries}))
            tag = "retrom-core-gf65d5ba9bc42-r2"
            with patch("release_archive.subprocess.check_output", return_value="a" * 40 + "\n"):
                first = build_archive(root, candidate, root / "first", tag)
                second = build_archive(root, candidate, root / "second", tag)
            self.assertEqual((root / "first/mame-current-assets.zip").read_bytes(),
                             (root / "second/mame-current-assets.zip").read_bytes())
            with zipfile.ZipFile(root / "first/mame-current-assets.zip") as archive:
                self.assertEqual(["LICENSES.txt", "mame-apple.wasm", "mame-common.wasm"], archive.namelist())
                self.assertEqual(payloads["mame-common.wasm"], archive.read("mame-common.wasm"))
            self.assertEqual(entries, first["files"])
            self.assertEqual("a" * 40, first["commit"])
            (candidate / "mame-common.wasm").write_bytes(b"corrupt")
            with patch("release_archive.subprocess.check_output", return_value="a" * 40 + "\n"):
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    build_archive(root, candidate, root / "third", tag)


if __name__ == "__main__":
    unittest.main()
