import {readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const root = process.argv[2];
const family = process.argv[3];
const destination = process.argv[4];
if (!root || !family || !destination || !/^[a-z0-9_]+$/u.test(family)) throw new Error('Build directory, family and output required');
const manifest = JSON.parse(await readFile(join(root, 'manifest.json'), 'utf8'));
if (manifest.families[family]?.arcade !== true) throw new Error('Arcade family required');
const asset = name => join(root, manifest.assets[name].path);
const {default: factory} = await import(pathToFileURL(asset('mame-common.mjs')).href);
const module = await factory({wasmBinary: await readFile(asset('mame-common.wasm')),
  locateFile: name => join(root, name), print: () => {}, printErr: () => {}});
await module.loadDynamicLibrary(manifest.assets[`mame-${family}.wasm`].path, {global: true, nodelete: true, loadAsync: true});
if (module._retrom_mame_attach() !== 0) throw new Error('Arcade family registration failed');
module.FS.mkdirTree('/content');
if (module._retrom_mame_listxml() !== 1) throw new Error('MAME listxml failed');
const bytes = module.FS.readFile('/content/mame-arcade.xml');
if (!bytes.length) throw new Error('MAME listxml empty');
await writeFile(destination, bytes);
