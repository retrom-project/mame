#!/usr/bin/env python3
"""Build a compact, exact-build Arcade DAT from each linked driver family."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
KEEP = {"description", "year", "manufacturer", "biosset", "rom", "disk", "sample", "device_ref"}
ATTRS = {"name", "cloneof", "romof", "isbios", "isdevice", "runnable"}


def compact_machine(machine):
    compact = ET.Element("machine", {key: value for key, value in machine.attrib.items() if key in ATTRS})
    compact.extend(child for child in machine if child.tag in KEEP)
    # MAME selects the first system BIOS when ROM_DEFAULT_BIOS is absent
    # (device.cpp). Its XML omits "default" in that case.
    biossets = compact.findall("biosset")
    if biossets and not any(bios.get("default") == "yes" for bios in biossets):
        biossets[0].set("default", "yes")
    return compact


def validate_roster(root, expected, family):
    machines = {m.get("name"): m for m in root if m.tag == "machine"}
    drivers = {name for name, m in machines.items() if m.get("isdevice") != "yes"}
    if drivers != expected:
        raise RuntimeError(f"MAME XML roster mismatch: {family} ({len(drivers)} vs {len(expected)})")
    for machine in machines.values():
        for ref in machine.findall("device_ref"):
            device = machines.get(ref.get("name"))
            if device is None or device.get("isdevice") != "yes":
                raise RuntimeError(f"Missing device: {family}/{ref.get('name')}")


def merge_machine(seen, compact):
    name = compact.get("name")
    # Devices shared by separate linked families must describe identical ROMs.
    payload = ET.canonicalize(ET.tostring(compact, encoding="unicode"), strip_text=True)
    if name in seen:
        if compact.get("isdevice") != "yes":
            raise RuntimeError(f"Duplicate Arcade machine: {name}")
        if seen[name] != payload:
            raise RuntimeError(f"Inconsistent Arcade device: {name}")
        return False
    seen[name] = payload
    return True


def generate(output: Path, node: Path):
    manifest = json.loads((output / "manifest.json").read_text())
    families = {name: details for name, details in manifest["families"].items()
                if details.get("arcade") is True}
    if not families:
        raise RuntimeError("No Arcade family in linked MAME build")
    with tempfile.TemporaryDirectory(prefix="arcade-dat.", dir=output) as temporary:
        temporary = Path(temporary)
        def extract(name):
            raw = temporary / (name + ".xml")
            subprocess.run([node, ROOT / "scripts/retrom/generate_arcade_dat.mjs", output, name, raw], check=True)
            tree = ET.parse(raw)
            root = tree.getroot()
            if root.tag != "mame":
                raise RuntimeError(f"MAME XML root invalid: {name}")
            expected = set(families[name]["drivers"]) - {"___empty"}
            validate_roster(root, expected, name)
            return name, raw
        with ThreadPoolExecutor(max_workers=min(4, len(families))) as pool:
            files = {pool.submit(extract, name): name for name in sorted(families)}
            for task in as_completed(files):
                task.result()
                print("Arcade DAT family:", files[task], flush=True)
        pending = output / "mame-arcade.xml.tmp"
        seen = {}
        try:
            with pending.open("wb") as target:
                target.write((f'<?xml version="1.0" encoding="utf-8"?>\n'
                              f'<mame retromBuildId="{manifest["buildId"]}">\n').encode())
                for name in sorted(families):
                    root = ET.parse(temporary / (name + ".xml")).getroot()
                    for machine in root:
                        if machine.tag != "machine":
                            continue
                        compact = compact_machine(machine)
                        if not merge_machine(seen, compact):
                            continue
                        target.write(ET.tostring(compact, encoding="utf-8"))
                        target.write(b"\n")
                target.write(b"</mame>\n")
            pending.replace(output / "mame-arcade.xml")
        finally:
            pending.unlink(missing_ok=True)
    print(f"Arcade DAT: {len(seen)} machines, {os.stat(output / 'mame-arcade.xml').st_size} bytes", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate_arcade_dat.py BUILD_DIR SDK_NODE")
    generate(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
