export async function verifiedBytes(asset, events, cacheStorage = globalThis.caches) {
  const url = new URL(asset.path, location.href).href;
  let cache;
  try { cache = await cacheStorage?.open('retrom-mame-poc-v1'); } catch {}
  async function verify(response) {
    if (!response?.ok) throw new Error(`Asset unavailable: ${asset.path}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map(x => x.toString(16).padStart(2, '0')).join('');
    if (bytes.length !== asset.sizeBytes || digest !== asset.sha256) throw new Error(`Asset integrity: ${asset.path}`);
    return bytes;
  }
  let hit;
  try { hit = await cache?.match(url); } catch {}
  if (hit) {
    try {
      const bytes = await verify(hit);
      events.push({path: asset.path, source: 'cache', bytes: bytes.length});
      return bytes;
    } catch { try { await cache.delete(url); } catch {} }
  }
  const bytes = await verify(await fetch(url));
  try { await cache?.put(url, new Response(bytes)); } catch {}
  events.push({path: asset.path, source: 'network', bytes: bytes.length});
  return bytes;
}

export async function load(family, mode = 'dynamic', options = {}) {
  const manifest = await (await fetch('manifest.json', {cache: 'no-store'})).json();
  if (!Object.hasOwn(manifest.families, family)) throw new Error('Unknown family');
  if (!['static', 'dynamic'].includes(mode)) throw new Error('Unknown link mode');
  if (options.expectedBuildId && manifest.buildId !== options.expectedBuildId) throw new Error('Build mismatch');
  const events = [];
  const prefix = mode === 'dynamic' ? 'mame-common' : `mame-static-${family}`;
  const begin = performance.now();
  const [factory, wasmBinary] = await Promise.all([
    import('./' + manifest.assets[prefix + '.mjs'].path),
    verifiedBytes(manifest.assets[prefix + '.wasm'], events),
  ]);
  const module = await factory.default({wasmBinary, locateFile: path => new URL(path, location.href).href,
    print: console.log, printErr: console.warn});
  const commonReadyMs = performance.now() - begin;
  if (mode === 'dynamic') {
    const bytes = await verifiedBytes(manifest.assets[`mame-${family}.wasm`], events);
    const url = URL.createObjectURL(new Blob([bytes], {type: 'application/wasm'}));
    try {
      await module.loadDynamicLibrary(url, {global: true, nodelete: true, loadAsync: true});
    } finally { URL.revokeObjectURL(url); }
  }
  if (module._retrom_mame_attach() !== 0) throw new Error('Family registration or build mismatch');
  return {module, events, manifest, family, mode, commonReadyMs, linkedMs: performance.now() - begin};
}
