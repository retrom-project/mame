#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Generate original diagnostic firmware. No commercial BIOS or game bytes.

The firmware runs on the unmodified Apple II+, Atom and PV-1000 machine drivers.
Apple/Atom ROM audit checksum warnings are expected: these are intentionally
original replacement programs, not copies of the vendor firmware.
"""
import hashlib
import json
from pathlib import Path
import sys


class Program:
    def __init__(self, origin):
        self.origin, self.code, self.labels, self.fixups = origin, bytearray(), {}, []

    def emit(self, *values):
        self.code.extend(values)

    def label(self, name):
        self.labels[name] = self.origin + len(self.code)

    def branch(self, opcode, name):
        self.emit(opcode, 0)
        self.fixups.append((len(self.code) - 1, name, True))

    def jump(self, opcode, name):
        self.emit(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, name, False))

    def finish(self):
        for offset, name, relative in self.fixups:
            address = self.labels[name]
            if relative:
                delta = address - (self.origin + offset + 1)
                if not -128 <= delta <= 127:
                    raise ValueError("Branch out of range")
                self.code[offset] = delta & 255
            else:
                self.code[offset:offset + 2] = address.to_bytes(2, "little")
        return bytes(self.code)


def firmware6502(kind):
    apple = kind == "apple"
    origin = 0xf800 if apple else 0xf000
    p = Program(origin)
    p.emit(0x78, 0xd8, 0xa2, 0xff, 0x9a)  # SEI, CLD, LDX #ff, TXS
    p.emit(0xa9, 0, 0x85, 0x20, 0x85, 0x21)  # durable input state and speaker phase
    if apple:
        for switch in (0x50, 0x52, 0x54, 0x56):
            p.emit(0xad, switch, 0xc0)  # full-screen low-resolution graphics
    else:
        p.emit(0xa9, 0x8a, 0x8d, 3, 0xb0)  # PPI: A output, B input, C low output
        p.emit(0xa9, 0x12, 0x8d, 0, 0xb0)  # graphics mode and keyboard row 2
    p.emit(0xa2, 0)
    p.label("fill")
    p.emit(0x8a)  # TXA
    for page in ((4, 5, 6, 7) if apple else (0x80, 0x81, 0x82, 0x83)):
        p.emit(0x9d, 0, page)  # STA screen,X
    p.emit(0xe8)
    p.branch(0xd0, "fill")
    p.label("loop")
    if apple:
        p.emit(0xad, 0, 0xc0)  # keyboard data/strobe
        p.branch(0x10, "sound")
        p.emit(0x29, 0x7f, 0x85, 0x20, 0x8d, 0, 4, 0xad, 0x10, 0xc0)
    else:
        p.emit(0xad, 1, 0xb0, 0x49, 0xff, 0x29, 1)  # UP key, active low
        p.branch(0xf0, "sound")
        p.emit(0xa9, 0x33, 0x85, 0x20, 0x8d, 0, 0x80)
    p.label("sound")
    if apple:
        p.emit(0xad, 0x30, 0xc0)
    else:
        p.emit(0xa5, 0x21, 0x49, 4, 0x85, 0x21, 0x8d, 2, 0xb0)
    p.emit(0xa0, 0xff)
    p.label("delay")
    p.emit(0x88)
    p.branch(0xd0, "delay")
    p.jump(0x4c, "loop")
    rom = bytearray([0xea] * (0x10000 - origin))
    program = p.finish()
    rom[:len(program)] = program
    for offset in (-6, -4, -2):
        rom[len(rom) + offset:len(rom) + offset + 2] = origin.to_bytes(2, "little")
    return bytes(rom)


def firmware_z80():
    p = Program(0)
    p.emit(0xf3, 0x31, 0xf0, 0xbf)  # DI; LD SP,bff0
    p.emit(0x21, 0, 0xb8, 0x01, 0, 3)  # fill 768 tile map entries
    p.label("fill")
    p.emit(0x36, 4, 0x23, 0x0b, 0x78, 0xb1)
    p.branch(0x20, "fill")
    p.emit(0xaf, 0x32, 0x10, 0xb8)  # durable state
    for port, value in ((0xff, 0), (0xf8, 0x20), (0xfb, 2), (0xfd, 4)):
        p.emit(0x3e, value, 0xd3, port)
    p.label("loop")
    p.emit(0xdb, 0xfd, 0xe6, 3)
    p.branch(0x28, "loop")
    p.emit(0x3e, 5, 0x32, 0x10, 0xb8, 0x32, 0x42, 0xb8)
    p.jump(0xc3, "loop")
    rom = bytearray(8192)
    program = p.finish()
    rom[:len(program)] = program
    rom[4 * 32:5 * 32] = bytes([0x55, 0xaa] * 16)
    rom[5 * 32:6 * 32] = bytes([0xff] * 32)
    return bytes(rom)


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for family in ("apple", "acorn", "vintage"):
        files = {}
        if family == "apple":
            for name in ("341-0011.d0", "341-0012.d8", "341-0013.e0", "341-0014.e8", "341-0015.f0"):
                files["apple2p/" + name] = bytes([0xea] * 2048)
            files["apple2p/341-0020-00.f8"] = firmware6502(family)
            files["apple2p/341-0036.chr"] = bytes(2048)
            command = 'apple2p -sl4 "" -sl6 "" -rompath /content'
        elif family == "acorn":
            files["atom/abasic.ic20"] = bytes([0xea] * 4096) + firmware6502(family)
            files["atom/afloat.ic21"] = bytes(4096)
            command = 'atom -pl6 "" -rompath /content'
        else:
            files["diagnostic.bin"] = firmware_z80()
            command = "pv1000 -cart /content/diagnostic.bin"
        files["launch.cmd"] = (command + " -skip_gameinfo -nothrottle\n").encode()
        entries = []
        for name, data in files.items():
            path = output / family / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            entries.append({"path": family + "/" + name, "destination": "/content/" + name,
                            "sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        result[family] = {"files": entries, "address": 0xb810 if family == "vintage" else 0x20,
                          "key": 97 if family == "apple" else 273,
                          "expected": 65 if family == "apple" else 51 if family == "acorn" else 5}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    generate(Path(sys.argv[1]))
