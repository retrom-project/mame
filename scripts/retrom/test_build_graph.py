import unittest
from build_graph import closed_common


class SharedBoundaryTests(unittest.TestCase):
    def test_shared_device_with_private_dependency_remains_inside_families(self):
        definitions = {"bus": {"bus.o"}, "card": {"card.o"}, "cpu": {"cpu.o"}}
        required = {"bus.o": {"card"}, "cpu.o": {"memcpy"}}
        self.assertEqual(closed_common({"bus.o", "cpu.o"}, definitions, required), {"cpu.o"})

    def test_removal_propagates_to_shared_dependents(self):
        definitions = {"a": {"a.o"}, "b": {"b.o"}, "private": {"private.o"}}
        required = {"a.o": {"b"}, "b.o": {"private"}}
        self.assertEqual(closed_common({"a.o", "b.o"}, definitions, required), set())

    def test_closed_cycle_and_alternate_weak_definition_can_be_shared(self):
        definitions = {"a": {"a.o"}, "b": {"b.o"}, "helper": {"a.o", "private.o"}}
        required = {"a.o": {"b"}, "b.o": {"a", "helper"}}
        self.assertEqual(closed_common({"a.o", "b.o"}, definitions, required), {"a.o", "b.o"})


if __name__ == "__main__":
    unittest.main()
