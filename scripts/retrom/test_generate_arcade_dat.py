import unittest
import xml.etree.ElementTree as ET

from generate_arcade_dat import compact_machine, merge_machine, validate_roster


class CompactMachineTest(unittest.TestCase):
    def test_shared_device_is_deduplicated_but_inconsistent_facts_fail(self):
        seen = {}
        device = ET.fromstring('<machine name="mcu" isdevice="yes" runnable="no"><rom name="boot" size="1" crc="12345678"/></machine>')
        self.assertTrue(merge_machine(seen, device))
        self.assertFalse(merge_machine(seen, ET.fromstring(ET.tostring(device))))
        device.find('rom').set('size', '2')
        with self.assertRaisesRegex(RuntimeError, 'Inconsistent'):
            merge_machine(seen, device)

    def test_duplicate_playable_machine_fails(self):
        seen = {}
        machine = ET.fromstring('<machine name="game"/>')
        merge_machine(seen, machine)
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            merge_machine(seen, machine)

    def test_roster_separates_drivers_from_device_dependencies(self):
        root = ET.fromstring('<mame><machine name="game"><device_ref name="mcu"/></machine><machine name="mcu" isdevice="yes" runnable="no"/></mame>')
        validate_roster(root, {'game'}, 'test')
        root.remove(root.find("machine[@name='mcu']"))
        with self.assertRaisesRegex(RuntimeError, 'Missing device'):
            validate_roster(root, {'game'}, 'test')

    def test_device_identity_and_references_survive_compaction(self):
        machine = ET.fromstring('<machine name="mcu" isdevice="yes" runnable="no">'
                               '<device_ref name="child"/><rom name="bootstrap.bin" size="115"/>'
                               '<display type="raster"/></machine>')
        compact = compact_machine(machine)
        self.assertEqual(compact.attrib, {"name": "mcu", "isdevice": "yes", "runnable": "no"})
        self.assertEqual(compact.find("device_ref").get("name"), "child")
        self.assertEqual(compact.find("rom").get("name"), "bootstrap.bin")
        self.assertIsNone(compact.find("display"))

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
