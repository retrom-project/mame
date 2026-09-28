// SPDX-License-Identifier: BSD-3-Clause
// CPU/quickload regression using only diagnostics.py's original firmware.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root = resolve(process.argv[2]);
const diagnostics = resolve(process.argv[3]);
const create = (await import(pathToFileURL(root + '/mame-common.mjs'))).default;
const m = await create({wasmBinary: readFileSync(root + '/mame-common.wasm'), noInitialRun: true, print() {}, printErr() {}});
await m.loadDynamicLibrary('mame-acorn.wasm', {global: true, nodelete: true, loadAsync: true});
assert.equal(m._retrom_mame_attach(), 0);
m.FS.mkdirTree('/content/atom');
for (const name of ['abasic.ic20', 'afloat.ic21']) {
  m.FS.writeFile('/content/atom/' + name, readFileSync(diagnostics + '/acorn/atom/' + name));
}
// A quickloaded program writes a marker, then loops. It must replace an in-flight
// instruction from the boot firmware, not continue that old instruction's phase.
const program = new Uint8Array([0xa9, 0x5a, 0x85, 0x20, 0x4c, 0x04, 0x28]);
const atm = new Uint8Array(22 + program.length), header = new DataView(atm.buffer);
header.setUint16(16, 0x2800, true); header.setUint16(18, 0x2800, true); header.setUint16(20, program.length, true);
atm.set(program, 22); m.FS.writeFile('/content/probe.atm', atm);
m.FS.writeFile('/content/boot.cmd', 'atom -pl6 "" -quickload /content/probe.atm -rompath /content -skip_gameinfo -nothrottle');
const pointer = m._malloc(64); m.HEAPU8.set(new TextEncoder().encode('/content/boot.cmd\0'), pointer);
try {
  assert.equal(m._retrom_mame_start(pointer), 1);
  for (let i = 0; i < 240; i++) {assert.equal(m._retrom_mame_step(), 1);}
  assert.equal(m._retrom_mame_peek(0x2800), program[0], 'quickload copied program bytes');
  assert.equal(m._retrom_mame_peek(0x20), 0x5a, 'quickload executed the new program');
  console.log('quickload: PASS');
} finally {m._free(pointer); m._retrom_mame_stop();}
