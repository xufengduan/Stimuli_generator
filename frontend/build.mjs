import { build, transform } from 'esbuild';
import { readFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';

const css = await transform(await readFile('static/styles.css', 'utf8'), { loader: 'css', logLevel: 'silent' });
if (css.warnings.length) throw new Error(css.warnings.map(warning => warning.text).join('\n'));

await build({
    entryPoints: ['frontend/ui.jsx'],
    outfile: 'static/ui-react.js',
    bundle: true,
    minify: true,
    format: 'esm',
    target: ['es2020'],
    jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"' },
    legalComments: 'linked'
});
const bundle = await readFile('static/ui-react.js');
console.log(`React UI built: ${(bundle.length / 1024).toFixed(1)} KB / ${(gzipSync(bundle).length / 1024).toFixed(1)} KB gzip`);
