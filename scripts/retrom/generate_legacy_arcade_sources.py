#!/usr/bin/env python3
"""Snapshot MAME Current source families covering the pinned 2003/2003+ DAT names.

This is an inventory, not a claim that an old ROM ZIP matches Current's ROM
definitions.  Retrom validates each ZIP against the Current DAT separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def dat_names(path):
    root = ET.parse(path).getroot()
    if root.tag not in ("mame", "datafile"):
        raise ValueError(f"Unsupported DAT root: {path}")
    return {entry.attrib["name"] for entry in root if entry.tag in ("machine", "game")}


def source_index(path):
    result, source = {}, None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("@source:"):
            source = line.partition(":")[2].strip()
        elif source and re.fullmatch(r"[a-z0-9_]+", line):
            if line in result:
                raise ValueError(f"Duplicate MAME driver: {line}")
            result[line] = source
    return result


def generate(first, second):
    old = dat_names(first) | dat_names(second)
    current = source_index(ROOT / "src/mame/mame.lst")
    matched = old & current.keys()
    grouped = {}
    for machine in matched:
        source = current[machine]
        directory = source.split("/", 1)[0]
        name = "pacman" if directory == "pacman" else "arcade_" + directory
        grouped.setdefault(name, set()).add(source)
    families = {name: {"arcade": True, "sources": sorted(sources)}
                for name, sources in sorted(grouped.items())}
    document = {
        "schemaVersion": 1,
        "provenance": {key: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "machineCount": len(dat_names(path))}
                       for key, path in (("mame2003", first), ("mame2003_plus", second))},
        "oldMachineCount": len(old),
        "currentNameCount": len(matched),
        "absentCurrentNames": sorted(old - current.keys()),
        "requiredCurrentNames": sorted(matched),
        "families": families,
    }
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mame2003_dat", type=Path)
    parser.add_argument("mame2003_plus_dat", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "scripts/retrom/legacy_arcade_sources.json")
    args = parser.parse_args()
    result = generate(args.mame2003_dat, args.mame2003_plus_dat)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['currentNameCount']} current names in {len(result['families'])} source groups; "
          f"{len(result['absentCurrentNames'])} old names absent")
