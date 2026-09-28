import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {chromium} from 'playwright-core';

const origin = process.env.RETROM_POC_ORIGIN || 'http://localhost:4785';
const evidence = process.argv[2];
if (!evidence || !process.env.RETROM_CHROME_EXECUTABLE) throw new Error('Evidence directory and RETROM_CHROME_EXECUTABLE required');
await mkdir(evidence, {recursive: true});
const browser = await chromium.launch({executablePath: process.env.RETROM_CHROME_EXECUTABLE, headless: true,
  args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required']});
const context = await browser.newContext({viewport: {width: 960, height: 900}});
const report = {status: 'RUNNING', browser: browser.version(), cases: [], errors: []};
const deadline = setTimeout(() => { console.error('PoC browser deadline exceeded'); process.exit(124); }, 600000);

async function launch(family, mode) {
  const page = await context.newPage();
  const consoleLog = [];
  page.on('console', message => consoleLog.push(message.text()));
  page.on('pageerror', error => consoleLog.push(String(error)));
  await page.goto(`${origin}/run.html?family=${family}&mode=${mode}`);
  try {
    await page.waitForFunction(() => window.poc?.ready || window.pocError, undefined, {timeout: 120000});
    const error = await page.evaluate(() => window.pocError);
    if (error) throw new Error(error);
  } catch (error) {
    await writeFile(join(evidence, `${family}-${mode}-console.log`), consoleLog.join('\n'));
    throw error;
  }
  return page;
}

async function exercise(family, mode) {
  const page = await launch(family, mode);
  const initial = await page.evaluate(() => {
    const elapsedMs = window.poc.step(120);
    return {metrics: window.poc.metrics(), elapsedMs, state: window.poc.save(), image: document.querySelector('canvas').toDataURL()};
  });
  assert.equal(initial.metrics.state, 0, `${family}: diagnostic firmware booted`);
  assert(initial.metrics.frames > 30 && initial.metrics.width > 0, `${family}: rendered frames`);
  assert(initial.metrics.audioRms > 0, `${family}: non-silent PCM`);
  assert(initial.state.length > 0, `${family}: nonempty save`);
  const inputKey = family === 'apple' ? 'a' : 'ArrowUp';
  await page.keyboard.down(inputKey);
  await page.evaluate(() => window.poc.step(6));
  await page.keyboard.up(inputKey);
  const changed = await page.evaluate(() => {
    window.poc.step(2);
    return {metrics: window.poc.metrics(), expected: window.poc.diagnostic.expected,
      image: document.querySelector('canvas').toDataURL(), duplicateAttach: window.poc.duplicateAttach()};
  });
  assert.equal(changed.metrics.state, changed.expected, `${family}: input reached the emulated program`);
  assert.notEqual(changed.image, initial.image, `${family}: input changed rendered output`);
  assert.equal(changed.duplicateAttach, -3, 'Reject a second driver registration');
  await page.screenshot({path: join(evidence, `${family}-${mode}.png`)});
  await page.close();
  const restored = await launch(family, mode);
  const result = await restored.evaluate(bytes => {
    window.poc.step(120);
    window.poc.key(window.poc.diagnostic.key, true);
    window.poc.step(6);
    window.poc.key(window.poc.diagnostic.key, false);
    window.poc.step(2);
    const beforeRestore = window.poc.peek();
    window.poc.restore(bytes);
    const restoredState = window.poc.peek();
    window.poc.key(window.poc.diagnostic.key, true);
    window.poc.step(6);
    window.poc.key(window.poc.diagnostic.key, false);
    window.poc.step(2);
    return {beforeRestore, restoredState, resumedState: window.poc.peek(), metrics: window.poc.metrics()};
  }, initial.state);
  assert.equal(result.beforeRestore, changed.expected, `${family}: fresh instance changed before restore`);
  assert.equal(result.restoredState, 0, `${family}: fresh instance restored initial state`);
  assert.equal(result.resumedState, changed.expected, `${family}: input after restore`);
  await restored.screenshot({path: join(evidence, `${family}-${mode}-restored.png`)});
  await restored.close();
  report.cases.push({family, mode, initial: initial.metrics, input: changed.metrics, restored: result,
    steps120Ms: initial.elapsedMs, saveBytes: initial.state.length});
  await writeFile(join(evidence, 'results.json'), JSON.stringify(report, null, 2));
}

try {
  // Each launch owns a new page/Module/Memory; only persistent bytes are shared.
  await exercise('apple', 'dynamic');
  await exercise('acorn', 'dynamic');
  const repeat = await launch('apple', 'dynamic');
  const repeatMetrics = await repeat.evaluate(() => window.poc.metrics());
  assert(repeatMetrics.events.every(event => event.source === 'cache'), 'A -> B -> A uses cached WASM');
  await repeat.close();
  await exercise('vintage', 'dynamic');
  for (const family of ['apple', 'acorn', 'vintage']) await exercise(family, 'static');
  const requests = await (await fetch(origin + '/__requests')).json();
  const common = requests.filter(request => /^mame-common\..*\.wasm$/.test(request.path));
  assert.equal(common.length, 1, 'Common WASM transferred exactly once across families and new instances');
  const probe = await context.newPage();
  await probe.goto(origin);
  const negative = await probe.evaluate(async () => {
    const {load, verifiedBytes} = await import('./loader.mjs');
    const errors = [];
    for (const [family, options] of [['missing', {}], ['apple', {expectedBuildId: 'wrong'}]]) {
      try { await load(family, 'dynamic', options); } catch (error) { errors.push(error.message); }
    }
    const manifest = await (await fetch('manifest.json')).json();
    const asset = manifest.assets['mame-common.wasm'];
    const cache = await caches.open('retrom-mame-poc-v1');
    await cache.put(new URL(asset.path, location.href), new Response('corrupt'));
    const events = [];
    await verifiedBytes(asset, events);
    const unavailableCache = {open() { throw new Error('storage unavailable'); }};
    const fallback = [];
    await verifiedBytes(asset, fallback, unavailableCache);
    // Alter only the descriptor's fixed-width build ID, preserving a valid
    // module, to exercise the native boundary rather than just a JS guard.
    const {default: factory} = await import('./' + manifest.assets['mame-common.mjs'].path);
    const module = await factory({wasmBinary: await verifiedBytes(asset, []),
      locateFile: path => new URL(path, location.href).href});
    const bytes = await verifiedBytes(manifest.assets['mame-apple.wasm'], []);
    const id = new TextEncoder().encode(manifest.buildId);
    let found = -1;
    outer: for (let offset = 0; offset <= bytes.length - id.length; offset++) {
      for (let j = 0; j < id.length; j++) if (bytes[offset + j] !== id[j]) continue outer;
      found = offset; break;
    }
    if (found < 0) throw new Error('Build descriptor absent');
    bytes[found] = bytes[found] === 48 ? 49 : 48;
    const url = URL.createObjectURL(new Blob([bytes], {type: 'application/wasm'}));
    let nativeMismatch;
    try {
      await module.loadDynamicLibrary(url, {global: true, nodelete: true, loadAsync: true});
      nativeMismatch = module._retrom_mame_attach();
    } finally { URL.revokeObjectURL(url); }
    return {errors, events, fallback, nativeMismatch};
  });
  assert.deepEqual(negative.errors, ['Unknown family', 'Build mismatch']);
  assert.equal(negative.events[0].source, 'network', 'Corrupt cache is refetched');
  assert.equal(negative.fallback[0].source, 'network', 'Cache unavailable falls back to network');
  assert.equal(negative.nativeMismatch, -2, 'Native descriptor rejects a mismatched family build');
  report.cache = {repeatMetrics, requestsBeforeFaultInjection: requests, negative};
  report.status = 'PASSED';
} catch (error) {
  report.status = 'FAILED'; report.errors.push(String(error.stack || error)); process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  await writeFile(join(evidence, 'results.json'), JSON.stringify(report, null, 2));
  await browser.close();
  console.log(JSON.stringify({status: report.status, cases: report.cases.length, errors: report.errors}));
}
