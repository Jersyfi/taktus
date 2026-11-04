// The design tokens resolved, and the stylesheet written from them (ADR-0177 §3).
//
// `tokens.json` is the owner's design system, copied unchanged; `taktus.tokens.json` is Taktus's
// own layer beside it, every value a reference to a primitive. The names follow the design
// system's own table (its `build/naming.js`): short, with the group in the prefix. Both
// `scripts/tokens.js` and `src/lib/design.test.ts` read the tokens through this module only.

/** @typedef {{ $value: unknown, $type?: string }} Token */
/** @typedef {{ name: string, value: string, resolved: unknown }} Declaration */

const PRIMITIVE_PREFIX = /** @type {Record<string, string | null>} */ ({
	color: null,
	space: 'sp',
	radius: 'r',
	borderWidth: 'bw',
	layer: 'z',
	fontFamily: 'font',
	fontWeight: 'fw',
	fontSize: 'fs',
	lineHeight: 'lh',
	duration: 'dur',
	easing: 'ease',
	breakpoint: 'bp'
});
const FAMILY_ALIAS = /** @type {Record<string, string>} */ ({ neutral: 'n' });
const SEMANTIC_ALIAS = /** @type {Record<string, string>} */ ({ elevation: 'shadow' });

/**
 * The custom property's name for a token's path, without the leading `--`.
 * @param {string[]} path
 * @returns {string}
 */
export function cssName(path) {
	const [root, group, ...rest] = path;
	if (root === 'primitive') {
		if (group === 'color') {
			const [family = '', ...step] = rest;
			return [FAMILY_ALIAS[family] ?? family, ...step].join('-');
		}
		const prefix = PRIMITIVE_PREFIX[group ?? ''];
		if (!prefix) throw new Error(`no name prefix for the primitive group "${group}"`);
		return [prefix, ...rest].join('-');
	}
	if (root === 'semantic') {
		const [, , semanticGroup = '', ...tail] = path;
		const named = [SEMANTIC_ALIAS[semanticGroup] ?? semanticGroup, ...tail];
		// Taktus's layer: `family.reproducible.hue` is `--family-reproducible`.
		if (named[named.length - 1] === 'hue') named.pop();
		return named.join('-');
	}
	if (root === 'motion' || root === 'layout') return [root, ...path.slice(1)].join('-');
	if (root === 'density') return ['density', ...path.slice(2)].join('-');
	throw new Error(`unexpected token root "${root}" in ${path.join('.')}`);
}

/**
 * Every token under a node, with its path.
 * @param {unknown} node
 * @param {string[]} path
 * @returns {[string[], Token][]}
 */
function leaves(node, path = []) {
	if (node === null || typeof node !== 'object') return [];
	if ('$value' in node) return [[path, /** @type {Token} */ (node)]];
	return Object.entries(node).flatMap(([key, child]) => (key.startsWith('$') ? [] : leaves(child, [...path, key])));
}

/**
 * The token a reference `{a.b.c}` names.
 * @param {Record<string, unknown>} tokens
 * @param {string} reference
 * @returns {[string[], Token]}
 */
function target(tokens, reference) {
	const path = reference.slice(1, -1).split('.');
	/** @type {unknown} */
	let node = tokens;
	for (const key of path) {
		node = node && typeof node === 'object' ? /** @type {Record<string, unknown>} */ (node)[key] : undefined;
	}
	if (!node || typeof node !== 'object' || !('$value' in node)) throw new Error(`the reference ${reference} names no token`);
	return [path, /** @type {Token} */ (node)];
}

const REFERENCE = /^\{[^}]+\}$/;

/**
 * A token's value with every reference followed.
 * @param {Record<string, unknown>} tokens
 * @param {Token} token
 * @returns {unknown}
 */
export function resolved(tokens, token) {
	let value = token.$value;
	for (let depth = 0; typeof value === 'string' && REFERENCE.test(value); depth += 1) {
		if (depth > 8) throw new Error(`a reference cycle at ${value}`);
		value = target(tokens, value)[1].$value;
	}
	return value;
}

/**
 * A resolved value as CSS.
 * @param {unknown} value
 * @param {string | undefined} type
 * @returns {string}
 */
function css(value, type) {
	if (type === 'fontFamily' && Array.isArray(value)) {
		return value.map((face) => (/^[a-z-]+$/.test(face) ? face : `"${face}"`)).join(', ');
	}
	if (type === 'cubicBezier' && Array.isArray(value)) return `cubic-bezier(${value.join(', ')})`;
	if (type === 'shadow' && Array.isArray(value)) {
		if (value.length === 0) return 'none';
		return value
			.map((s) => `${s.inset ? 'inset ' : ''}${s.offsetX} ${s.offsetY} ${s.blur} ${s.spread} ${s.color}`)
			.join(', ');
	}
	return String(value);
}

/**
 * A declaration: a direct reference stays a reference to the primitive's own property, so the
 * stylesheet shows where a value comes from.
 * @param {Record<string, unknown>} tokens
 * @param {string[]} path
 * @param {Token} token
 * @returns {Declaration}
 */
function declaration(tokens, path, token) {
	const value = resolved(tokens, token);
	const type = token.$type;
	const raw = token.$value;
	if (typeof raw === 'string' && REFERENCE.test(raw)) {
		const [to] = target(tokens, raw);
		return { name: cssName(path), value: `var(--${cssName(to)})`, resolved: value };
	}
	return { name: cssName(path), value: css(value, type), resolved: value };
}

/**
 * The two files merged into one tree: Taktus's semantic layer beside the design system's.
 * @param {Record<string, any>} foundation
 * @param {Record<string, any>} taktus
 * @returns {Record<string, any>}
 */
export function merged(foundation, taktus) {
	const semantic = { ...foundation.semantic };
	for (const mode of ['light', 'dark']) {
		const own = foundation.semantic?.[mode] ?? {};
		const added = taktus.semantic?.[mode] ?? {};
		for (const key of Object.keys(added)) {
			if (key in own) throw new Error(`Taktus's layer redefines the group semantic.${mode}.${key}`);
		}
		semantic[mode] = { ...own, ...added };
	}
	return { ...foundation, semantic };
}

/**
 * Every declaration, by where it is declared.
 * @param {Record<string, any>} tokens the merged tree
 */
export function declarations(tokens) {
	/** @param {unknown} node @param {string[]} path */
	const of = (node, path) => leaves(node, path).map(([p, t]) => declaration(tokens, p, t));
	const density = /** @type {Record<string, unknown>} */ (tokens.density ?? {});
	return {
		root: [...of(tokens.primitive, ['primitive']), ...of(tokens.motion, ['motion']), ...of(tokens.layout, ['layout'])],
		light: of(tokens.semantic.light, ['semantic', 'light']),
		dark: of(tokens.semantic.dark, ['semantic', 'dark']),
		density: Object.fromEntries(Object.keys(density).filter((mode) => !mode.startsWith("$")).map((mode) => [mode, of(density[mode], ['density', mode])]))
	};
}

/**
 * The stylesheet: primitives on `:root`, each mode under `[data-theme]`, and the system's choice
 * where the attribute is absent (ADR-0177 §3).
 * @param {Record<string, any>} tokens the merged tree
 * @returns {string}
 */
export function stylesheet(tokens) {
	const d = declarations(tokens);
	/** @param {string} selector @param {Declaration[]} list @param {string} [indent] */
	const block = (selector, list, indent = '') =>
		`${indent}${selector} {\n${list.map((x) => `${indent}\t--${x.name}: ${x.value};`).join('\n')}\n${indent}}\n`;
	const parts = [
		'/* Generated by web/scripts/tokens.js from web/design/ (ADR-0177). Never edited by hand. */\n',
		block(':root', d.root),
		block(':root, :root[data-density="comfortable"]', d.density.comfortable ?? []),
		...Object.entries(d.density)
			.filter(([mode]) => mode !== 'comfortable')
			.map(([mode, list]) => block(`:root[data-density="${mode}"]`, list)),
		block(':root:not([data-theme]), :root[data-theme="light"]', d.light).replace('{', '{\n\tcolor-scheme: light;'),
		block(':root[data-theme="dark"]', d.dark).replace('{', '{\n\tcolor-scheme: dark;'),
		'@media (prefers-color-scheme: dark) {\n' +
			block(':root:not([data-theme])', d.dark, '\t').replace('{', '{\n\t\tcolor-scheme: dark;') +
			'}\n'
	];
	return parts.join('\n');
}
