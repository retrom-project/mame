import json
from pathlib import Path
import unittest

from generate_legacy_arcade_sources import source_index


ROOT = Path(__file__).resolve().parents[2]


class LegacyArcadeSourcesTest(unittest.TestCase):
    def test_pinned_old_names_are_covered_by_selected_current_source_families(self):
        inventory = json.loads((ROOT / "scripts/retrom/legacy_arcade_sources.json").read_text())
        index = source_index(ROOT / "src/mame/mame.lst")
        required = inventory["requiredCurrentNames"]
        selected = {source for family in inventory["families"].values() for source in family["sources"]}
        self.assertEqual(5294, inventory["oldMachineCount"])
        self.assertEqual(4377, len(required))
        self.assertEqual(917, len(inventory["absentCurrentNames"]))
        self.assertEqual(83, len(inventory["families"]))
        self.assertEqual(required, sorted(set(required)))
        self.assertTrue(all(index.get(machine) in selected for machine in required))
        self.assertTrue(set(inventory["absentCurrentNames"]).isdisjoint(index))


if __name__ == "__main__":
    unittest.main()
