// After the build: the page's references to the app's own files, made relative.
//
// The app is served under `{prefix}/app/`, and the prefix is set when an instance starts, not
// when the app is built (ADR-0063). With the hash router SvelteKit writes the page's script and
// style references from the root (`/_app/...`); everything else it builds is already relative.
// This rewrites those references to `./_app/...`, and fails the build when none was found, so
// that a change in how SvelteKit writes the page is noticed rather than shipped.
import { readFileSync, writeFileSync } from 'node:fs';

const page = 'build/index.html';
const before = readFileSync(page, 'utf8');
const after = before.replaceAll(/(["'(])\/_app\//g, '$1./_app/');
if (after === before) {
	console.error(`${page}: no reference to /_app/ found; check how the page is written`);
	process.exit(1);
}
if (/["'(]\/_app\//.test(after)) {
	console.error(`${page}: a reference from the root is left`);
	process.exit(1);
}
writeFileSync(page, after);
console.log(`${page}: every reference to the app's files is relative`);
