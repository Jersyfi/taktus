// Before every script that reads the app: the design tokens written as one stylesheet,
// `src/lib/generated/tokens.css` (ADR-0177 §3). The file is never stored and never edited.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { merged, stylesheet } from '../design/resolve.js';

const read = (/** @type {string} */ path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const tokens = merged(read('../design/tokens.json'), read('../design/taktus.tokens.json'));
const out = new URL('../src/lib/generated/tokens.css', import.meta.url);
mkdirSync(new URL('.', out), { recursive: true });
writeFileSync(out, stylesheet(tokens));
console.log('tokens: src/lib/generated/tokens.css written from design/');
