// SPDX-License-Identifier: BSD-3-Clause
// Native startup/checkpoint regression using original diagnostic firmware only.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root = resolve(process.argv[2]);
const create = (await import(pathToFileURL(root + '/mame-common.mjs'))).default;
const family = process.argv[3] ?? 'coleco';
assert.ok(['coleco', 'sg1000', 'vintage'].includes(family));

// The Z80 updates a counter in machine RAM at an observable rate.
// No firmware/game bytes from the original systems are used.
const address = family === 'coleco' ? 0x6000 : family === 'sg1000' ? 0xc000 : 0xb800;
// An 8 KiB SG cartridge is detected as the X-Terminator accessory by MAME.
const rom = new Uint8Array(family === 'sg1000' ? 32768 : 8192);
rom.set([0xf3, 0x31, (address + 0x3f0) & 255, (address + 0x3f0) >> 8,
  0x21, address & 255, address >> 8, 0x36, 0, // counter = 0
  0x34, 0x01, 0xff, 0x1f, 0x0b, 0x78, 0xb1, 0x20, 0xfb, 0xc3, 9, 0]);
async function boot() {
  const m = await create({wasmBinary: readFileSync(root + '/mame-common.wasm'),
    locateFile: name => root + '/' + name, print() {}, printErr() {}});
  await m.loadDynamicLibrary('mame-' + family + '.wasm', {global: true, nodelete: true, loadAsync: true});
  assert.equal(m._retrom_mame_attach(), 0);
  m.FS.mkdirTree('/content/coleco');
  if (family === 'coleco') m.FS.writeFile('/content/coleco/313_10031-4005_73108a.u2', rom);
  m.FS.writeFile('/content/test.bin', rom);
  const machine = family === 'vintage' ? 'pv1000' : family;
  m.FS.writeFile('/content/boot.cmd', machine + ' -cart /content/test.bin -rompath /content -skip_gameinfo -nothrottle');
  const path = m._malloc(64);
  try {
    m.HEAPU8.set(new TextEncoder().encode('/content/boot.cmd\0'), path);
    assert.equal(m._retrom_mame_start(path), 1);
    assert.ok(m._retrom_mame_frames() > 0, 'start must return after emulation and a real video frame');
    assert.ok(m._retrom_mame_width() > 0);
    assert.ok(m._retrom_mame_save_size() > 0, 'native driver must support real serialization');
    return m;
  } catch (error) {m._retrom_mame_stop(); throw error;}
  finally {m._free(path);}
}
function step(m, count) {for (let i = 0; i < count; i++) assert.equal(m._retrom_mame_step(), 1);}
function save(m) {
  const size = m._retrom_mame_save_size(), pointer = m._malloc(size);
  try {
    assert.equal(m._retrom_mame_save(pointer, size), 1);
    return m.HEAPU8.slice(pointer, pointer + size);
  } finally {m._free(pointer);}
}
function restore(m, state) {
  const pointer = m._malloc(state.length);
  try {m.HEAPU8.set(state, pointer); assert.equal(m._retrom_mame_restore(pointer, state.length), 1);}
  finally {m._free(pointer);}
}
const warm = await boot();
try {
  step(warm, 90);
  const saved = warm._retrom_mame_peek(address), state = save(warm);
  step(warm, 45);
  const continued = warm._retrom_mame_peek(address);
  assert.notEqual(continued, saved, 'guest CPU continues execution');
  const cold = await boot();
  try {
    restore(cold, state);
    assert.equal(cold._retrom_mame_peek(address), saved, 'cold restore returns native RAM');
    step(cold, 45);
    assert.equal(cold._retrom_mame_peek(address), continued, 'cold execution resumes the saved CPU/timer state');
  } finally {cold._retrom_mame_stop();}
} finally {warm._retrom_mame_stop();}
console.log(family + ' startup and cold checkpoint: PASS');
