// The design system as the web app uses it (ADR-0177): every colour it shows measured for
// contrast in both modes, no colour written outside the tokens, and no custom property used
// that nothing declares.

import { describe, expect, it } from 'vitest';
import foundation from '../../design/tokens.json';
import taktus from '../../design/taktus.tokens.json';
import { declarations, merged, stylesheet } from '../../design/resolve.js';

type Declaration = { name: string; value: string; resolved: unknown };
const tokens = merged(foundation, taktus);
const declared = declarations(tokens) as {
	root: Declaration[];
	light: Declaration[];
	dark: Declaration[];
	density: Record<string, Declaration[]>;
};

function mode(name: 'light' | 'dark'): Map<string, string> {
	const values = new Map<string, string>();
	for (const d of [...declared.root, ...declared[name]]) values.set(d.name, String(d.resolved));
	return values;
}

/** The relative luminance of an opaque `#RRGGBB` (WCAG 2.2). */
function luminance(hex: string): number {
	const match = /^#([0-9a-f]{6})$/i.exec(hex);
	if (!match) throw new Error(`${hex} is not an opaque colour`);
	const channel = (i: number) => {
		const c = parseInt(match[1]!.slice(i, i + 2), 16) / 255;
		return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
	};
	return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

function contrast(a: string, b: string): number {
	const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p) as [number, number];
	return (x + 0.05) / (y + 0.05);
}

const PLANES = ['bg-canvas', 'bg-surface', 'bg-raised', 'bg-surface-sunken'];
const TEXTS = [
	'text-primary',
	'text-secondary',
	'text-subtle',
	'text-brand',
	'text-danger',
	'text-success',
	'text-warning',
	'ai-text'
];
const MARKS = [
	'family-reproducible',
	'family-variable',
	'family-person',
	'family-waiting',
	'family-alert',
	'chart-series-1',
	'chart-series-2',
	'chart-kind-input',
	'chart-kind-cache_write',
	'chart-kind-cache_read',
	'chart-kind-output',
	'focus-ring',
	'accent-primary',
	'border-default'
];

describe('the tokens in both modes', () => {
	for (const name of ['light', 'dark'] as const) {
		const values = mode(name);
		const value = (token: string) => {
			const found = values.get(token);
			if (!found) throw new Error(`no token ${token} in ${name}`);
			return found;
		};

		it(`sets text at 4.5:1 on every plane in ${name} (SC 1.4.3)`, () => {
			for (const text of TEXTS) {
				for (const plane of PLANES) {
					expect(contrast(value(text), value(plane)), `${text} on ${plane}`).toBeGreaterThanOrEqual(4.5);
				}
			}
		});

		it(`sets every status text on its own surface at 4.5:1 in ${name}`, () => {
			for (const status of ['info', 'success', 'warning', 'danger', 'neutral']) {
				expect(contrast(value(`status-${status}-text`), value(`status-${status}-surface`)), status).toBeGreaterThanOrEqual(4.5);
			}
		});

		it(`draws every family's mark, every chart series and the focus ring at 3:1 in ${name} (SC 1.4.11)`, () => {
			for (const mark of MARKS) {
				for (const plane of ['bg-canvas', 'bg-surface']) {
					expect(contrast(value(mark), value(plane)), `${mark} on ${plane}`).toBeGreaterThanOrEqual(3);
				}
			}
		});

		it(`gives each family a surface its text stays readable on in ${name}`, () => {
			for (const family of ['reproducible', 'variable', 'person', 'waiting', 'alert']) {
				expect(contrast(value('text-primary'), value(`family-${family}-surface`)), family).toBeGreaterThanOrEqual(4.5);
			}
		});
	}

	it('declares the same names in both modes', () => {
		expect(declared.light.map((d) => d.name).sort()).toEqual(declared.dark.map((d) => d.name).sort());
	});

	it("takes every value of Taktus's layer from a primitive, never a literal (ADR-0177 §2)", () => {
		const walk = (node: unknown): string[] =>
			node && typeof node === 'object'
				? '$value' in node
					? [String((node as { $value: unknown }).$value)]
					: Object.entries(node).flatMap(([k, v]) => (k.startsWith('$') ? [] : walk(v)))
				: [];
		const values = walk(taktus);
		expect(values.length).toBeGreaterThan(0);
		for (const v of values) expect(v).toMatch(/^\{primitive\.color\.[a-z]+\.\d+\}$/);
		// The signature carries no system meaning (ADR-0177 §2): no family and no series takes it.
		expect(values.filter((v) => v.includes('raspberry'))).toEqual([]);
	});
});

// --- the components bind to tokens, and only to tokens -------------------------------------------

/** Every component, module and stylesheet of the app, as its source; the generated ones aside. */
const SOURCES = Object.entries(
	import.meta.glob(['../**/*.svelte', '../**/*.ts', '../**/*.css', '!../**/*.test.ts', '!../**/generated/**'], {
		query: '?raw',
		import: 'default',
		eager: true
	}) as Record<string, string>
).map(([path, source]) => ({ path: path.replace(/^\.\.\//, ''), source }));

/** What of a file is style: its `<style>` blocks and every `style` attribute or directive. */
function styleOf(source: string, path: string): string {
	if (path.endsWith('.ts')) return '';
	if (path.endsWith('.css')) return source.replace(/\/\*[\s\S]*?\*\//g, '');
	const blocks = [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]);
	const attributes = [...source.matchAll(/\sstyle(?::[\w-]+)?=(?:"([^"]*)"|\{([^}]*)\})/g)].map((m) => m[1] ?? m[2]);
	// A comment is no style: an issue number such as `#224` is no colour.
	return [...blocks, ...attributes].join('\n').replace(/\/\*[\s\S]*?\*\//g, '');
}

const LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(/;

describe('the components', () => {
	const sources = SOURCES;
	const known = new Set(stylesheet(tokens).match(/--[\w-]+(?=:)/g) ?? []);

	it('are all read', () => {
		expect(sources.some((s) => s.path === 'app.css')).toBe(true);
		expect(sources.some((s) => s.path === 'routes/+layout.svelte')).toBe(true);
		expect(sources.length).toBeGreaterThan(80);
	});

	it('write no colour of their own (ADR-0177 §4)', () => {
		const found = sources.flatMap(({ path, source }) =>
			styleOf(source, path)
				.split('\n')
				.filter((line) => LITERAL.test(line))
				.map((line) => `${path}: ${line.trim()}`)
		);
		expect(found).toEqual([]);
	});

	// UC-13.7 §2 binds every type size of the frame to a token, and the radii follow the same rule
	// (ADR-0177 §4). The test held colours only until NTC-0289; 140 literal sizes and 78 literal
	// radii had passed it.
	it('write no type size and no radius of their own (NTC-0289)', () => {
		const declaration = /(font-size|border(?:-[a-z]+)*-radius)\s*:\s*([^;{}]+)/g;
		const literal = /(?<![\w-])\d*\.?\d+(px|rem|em|pt|%)(?![\w-])/;
		const found = sources.flatMap(({ path, source }) =>
			[...styleOf(source, path).matchAll(declaration)]
				.filter((m) => literal.test(m[2]!.replace(/\d*\.?\d+vw/g, '')))
				.map((m) => `${path}: ${m[0].trim()}`)
		);
		expect(found).toEqual([]);
	});

	it('use no custom property that no token and no rule of their own declares', () => {
		const found: string[] = [];
		for (const { path, source } of sources) {
			const own = new Set([
				...(source.match(/--[\w-]+(?=\s*:)/g) ?? []),
				...[...source.matchAll(/style:(--[\w-]+)/g)].map((m) => m[1]!)
			]);
			for (const m of source.matchAll(/var\((--[\w-]+)/g)) {
				if (!known.has(m[1]!) && !own.has(m[1]!)) found.push(`${path}: ${m[1]}`);
			}
		}
		expect(found).toEqual([]);
	});
});
