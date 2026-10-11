from pathlib import Path
import unittest

from build import load_families
from generate_legacy_arcade_sources import source_index


ROOT = Path(__file__).resolve().parents[2]


class CurrentArcadeSourcesTest(unittest.TestCase):
    def test_current_import_machines_have_compiled_drivers(self):
        machines = (
            "crysking denseib ffight3b bballoon dendego dendego2 hyperbbc kingdrbb "
            "renju tarzanc topbladv twrshaft gradius4 megaphx slrassltj starsldr "
            "shikigam mk4 coolridr finalapr gticlub midnrun ppcar speedrcr speedup "
            "wheelfir windheat bmcbowl evosocc fiveside nbapbp pokechmp skimaxx ttchamp"
        ).split()
        families, legacy = load_families()
        index = source_index(ROOT / "src/mame/mame.lst")
        selected = {source for family in families.values() for source in family["sources"]}
        missing = [machine for machine in machines if index.get(machine) not in selected]
        self.assertEqual([], missing)
        self.assertTrue(all(index[machine] in selected for machine in legacy["requiredCurrentNames"]))
        for family in families.values():
            self.assertEqual(len(family["sources"]), len(set(family["sources"])))

    def test_pilot_keeps_its_small_source_selection(self):
        families, _ = load_families(pilot=True)
        self.assertEqual(7, len(families))
        self.assertTrue(families["pacman"]["arcade"])


if __name__ == "__main__":
    unittest.main()
