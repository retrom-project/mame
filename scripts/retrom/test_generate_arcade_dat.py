import unittest
import xml.etree.ElementTree as ET

from generate_arcade_dat import compact_machine


class CompactMachineTest(unittest.TestCase):
    def test_implicit_default_uses_first_mame_bios(self):
        machine = ET.fromstring('<machine name="board"><biosset name="first"/><biosset name="second"/></machine>')
        compact = compact_machine(machine)
        self.assertEqual([entry.get("default") for entry in compact.findall("biosset")], ["yes", None])

    def test_explicit_default_is_preserved(self):
        machine = ET.fromstring('<machine name="board"><biosset name="first"/><biosset name="second" default="yes"/></machine>')
        compact = compact_machine(machine)
        self.assertEqual([entry.get("default") for entry in compact.findall("biosset")], [None, "yes"])


if __name__ == "__main__":
    unittest.main()
