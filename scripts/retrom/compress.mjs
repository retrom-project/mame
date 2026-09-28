import {readdir, readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {brotliCompress, brotliDecompress, gzip, gunzip, constants} from 'node:zlib';
import {promisify} from 'node:util';
const root = process.argv[2];
const previous = process.argv[3];
const compressBrotli = promisify(brotliCompress), compressGzip = promisify(gzip);
async function cached(file, bytes, decode) {
  if (!previous) return;
  try {
    const compressed = await readFile(join(previous, file));
    if ((await promisify(decode)(compressed)).equals(bytes)) return compressed;
  } catch {}
}
await Promise.all((await readdir(root)).filter(file => /\.(wasm|mjs)$/.test(file)).map(async file => {
  const bytes = await readFile(join(root, file));
  await writeFile(join(root, file + '.gz'), await cached(file + '.gz', bytes, gunzip) ?? await compressGzip(bytes, {level: 9}));
  await writeFile(join(root, file + '.br'), await cached(file + '.br', bytes, brotliDecompress) ?? await compressBrotli(bytes, {
    params: {[constants.BROTLI_PARAM_QUALITY]: 11},
  }));
}));
