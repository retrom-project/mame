import {load, verifiedBytes} from './loader.mjs';
const params = new URLSearchParams(location.search);
const family = params.get('family') || 'apple', mode = params.get('mode') || 'dynamic';
const canvas = document.querySelector('canvas'), status = document.querySelector('#status');
let playing = false, saved, audioContext, audioTime = 0;

async function start() {
  const instance = await load(family, mode);
  const {module: m, events} = instance;
  const diagnostics = await (await fetch('diagnostics/manifest.json')).json();
  const diagnostic = diagnostics[family];
  m.FS.mkdirTree('/content');
  for (const file of diagnostic.files) {
    m.FS.mkdirTree(file.destination.slice(0, file.destination.lastIndexOf('/')));
    m.FS.writeFile(file.destination, await verifiedBytes({...file, path: 'diagnostics/' + file.path}, []));
  }
  const startTime = performance.now();
  if (!m.ccall('retrom_mame_start', 'number', ['string'], ['/content/launch.cmd'])) throw new Error('Machine failed to start');
  const startupMs = performance.now() - startTime;
  let audioEnergy = 0, audioSamples = 0;
  function draw() {
    const width = m._retrom_mame_width(), height = m._retrom_mame_height();
    if (!width || !height) return;
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    const rgba = new Uint8ClampedArray(width * height * 4);
    const source = m.HEAPU8.subarray(m._retrom_mame_pixels(), m._retrom_mame_pixels() + rgba.length);
    for (let i = 0; i < rgba.length; i += 4) {
      rgba[i] = source[i + 2]; rgba[i + 1] = source[i + 1]; rgba[i + 2] = source[i]; rgba[i + 3] = 255;
    }
    canvas.getContext('2d').putImageData(new ImageData(rgba, width, height), 0, 0);
  }
  function step(count = 1) {
    const begin = performance.now();
    for (let i = 0; i < count; i++) {
      if (!m._retrom_mame_step()) throw new Error('Machine stopped');
      const samples = m.HEAP16.subarray(m._retrom_mame_audio() / 2, m._retrom_mame_audio() / 2 + m._retrom_mame_audio_count());
      for (const sample of samples) audioEnergy += (sample / 32768) ** 2;
      audioSamples += samples.length;
      if (audioContext && samples.length) {
        const buffer = audioContext.createBuffer(2, samples.length / 2, 48000);
        for (let channel = 0; channel < 2; channel++) {
          const target = buffer.getChannelData(channel);
          for (let j = 0; j < target.length; j++) target[j] = samples[j * 2 + channel] / 32768;
        }
        const source = audioContext.createBufferSource();
        source.buffer = buffer; source.connect(audioContext.destination);
        audioTime = Math.max(audioTime, audioContext.currentTime);
        source.start(audioTime); audioTime += buffer.duration;
      }
    }
    const elapsedMs = performance.now() - begin;
    draw();
    status.textContent = JSON.stringify(window.poc.metrics(), null, 2);
    return elapsedMs;
  }
  function save() {
    const size = m._retrom_mame_save_size();
    if (!size || size > 64 * 1024 * 1024) throw new Error('Invalid state size');
    const pointer = m._malloc(size);
    if (!pointer) throw new Error('State allocation failed');
    try {
      if (!m._retrom_mame_save(pointer, size)) throw new Error('Save failed');
      return Array.from(m.HEAPU8.subarray(pointer, pointer + size));
    } finally { m._free(pointer); }
  }
  function restore(bytes) {
    const pointer = m._malloc(bytes.length);
    if (!pointer) throw new Error('State allocation failed');
    try {
      m.HEAPU8.set(bytes, pointer);
      if (!m._retrom_mame_restore(pointer, bytes.length)) throw new Error('Restore failed');
    } finally { m._free(pointer); }
  }
  window.poc = {
    ready: true, family, mode, events, diagnostic, step, save, restore,
    key: (id, down) => m._retrom_mame_key(id, Number(down)),
    button: (id, down) => m._retrom_mame_button(id, Number(down)),
    peek: () => m._retrom_mame_peek(diagnostic.address),
    duplicateAttach: () => m._retrom_mame_attach(),
    metrics: () => ({family, mode, commonReadyMs: instance.commonReadyMs, linkedMs: instance.linkedMs,
      startupMs, frames: m._retrom_mame_frames(), width: m._retrom_mame_width(), height: m._retrom_mame_height(),
      memoryBytes: m.HEAPU8.buffer.byteLength, audioSamples, audioRms: Math.sqrt(audioEnergy / Math.max(1, audioSamples)),
      state: m._retrom_mame_peek(diagnostic.address), events}),
  };
  step(5);
  status.textContent = JSON.stringify(window.poc.metrics(), null, 2);
  const key = event => event.key === 'ArrowUp' ? 273 : event.key.length === 1 ? event.key.toLowerCase().charCodeAt(0) : 0;
  addEventListener('keydown', event => { if (key(event)) { event.preventDefault(); m._retrom_mame_key(key(event), 1); } });
  addEventListener('keyup', event => { if (key(event)) m._retrom_mame_key(key(event), 0); });
  addEventListener('blur', () => { for (let i = 0; i < 512; i++) m._retrom_mame_key(i, 0); });
  function tick() { if (playing) { step(); requestAnimationFrame(tick); } }
  document.querySelector('#play').onclick = async () => {
    audioContext ??= new AudioContext(); await audioContext.resume();
    playing = !playing; if (playing) tick(); canvas.focus();
  };
  document.querySelector('#save').onclick = () => { saved = save(); status.textContent = `已保存 ${saved.length} 字节`; };
  document.querySelector('#restore').onclick = () => { if (saved) { restore(saved); step(); status.textContent = '已恢复'; } };
}
start().catch(error => { window.pocError = String(error.stack || error); status.textContent = window.pocError; console.error(error); });
