import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from product_package import product_package


class ProductPackageTest(unittest.TestCase):
    def test_includes_full_legal_text_and_repeatable_candidate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs/legal").mkdir(parents=True)
            (root / "COPYING").write_text("MAME notice; see docs/legal/GPL-2.0")
            (root / "docs/legal/GPL-2.0").write_text("complete GPL text")
            sdk = root / "sdk"
            sdk.mkdir()
            (sdk / "LICENSE").write_text("complete Emscripten license")
            poc = root / "poc"
            poc.mkdir()
            assets = {}
            families = {"apple": ["apple2p", "apple2e"], "acorn": ["atom"],
                        "vintage": ["pv1000"], "pacman": ["mspacman", "puckman"]}
            for name in ("mame-common.mjs", "mame-common.wasm", *(f"mame-{family}.wasm" for family in families)):
                (poc / name).write_bytes(b"raw")
                (poc / (name + ".br")).write_bytes(b"br")
                assets[name] = {"path": name, "sha256": "a" * 64, "sizeBytes": 3}
            (poc / "manifest.json").write_text(json.dumps({"assets": assets, "buildId": "b" * 64, "emscripten": "3.1.74",
                                                      "families": {name: {"drivers": machines} for name, machines in families.items()}}))
            (poc / "mame-arcade.xml").write_text("<mame/>")
            def git(argv, **kwargs):
                return {"ls-files": b"COPYING\0docs/legal/GPL-2.0\0", "branch": b"feat/test", "rev-parse": b"c" * 40,
                        "status": b" M COPYING"}[argv[1]]
            outputs = []
            with patch("product_package.subprocess.check_output", side_effect=git):
                for name in ("first", "second"):
                    output = root / name
                    output.mkdir()
                    product_package(root, poc, output, sdk)
                    self.assertIn("complete GPL text", (output / "LICENSES.txt").read_text())
                    self.assertIn("complete Emscripten license", (output / "LICENSES.txt").read_text())
                    outputs.append({p.name: p.read_bytes() for p in output.iterdir()})
            self.assertEqual(outputs[0], outputs[1])
            descriptor = json.loads(outputs[0]["retrom-core-candidate.json"])
            self.assertEqual(15, len(descriptor["files"]))
            metadata = json.loads(outputs[0]["mame-build.json"])
            self.assertEqual(families,
                             {family: info["machines"] for family, info in metadata["families"].items()})


if __name__ == "__main__":
    unittest.main()
