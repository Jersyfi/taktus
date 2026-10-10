// How each token of the visual vocabulary becomes pixels (ADR-0059: the representation turns
// tokens into pixels and chooses no token itself). Every token the vocabulary names has its
// drawing here; a test fails a token that has none. Nothing here is a colour: the glyph is drawn
// in the page's current text colour, and every distinction is carried by form and motion.

const C = 50;

function polygon(sides: number, radius: number, rotation = -Math.PI / 2): string {
	const points: string[] = [];
	for (let i = 0; i < sides; i += 1) {
		const angle = rotation + (2 * Math.PI * i) / sides;
		points.push(`${(C + radius * Math.cos(angle)).toFixed(2)},${(C + radius * Math.sin(angle)).toFixed(2)}`);
	}
	return `M${points.join(' L')} Z`;
}

function rect(radius: number, corner: number): string {
	const a = C - radius;
	const b = C + radius;
	const r = corner;
	return `M${a + r},${a} H${b - r} Q${b},${a} ${b},${a + r} V${b - r} Q${b},${b} ${b - r},${b} H${a + r} Q${a},${b} ${a},${b - r} V${a + r} Q${a},${a} ${a + r},${a} Z`;
}

function ellipse(rx: number, ry: number): string {
	return `M${C - rx},${C} A${rx},${ry} 0 1 0 ${C + rx},${C} A${rx},${ry} 0 1 0 ${C - rx},${C} Z`;
}

/** The outline of each method kind, and of a run, as a path at a given radius. */
export const OUTLINES: Record<string, (radius: number) => string> = {
	square: (r) => rect(r * 0.85, 0),
	triangle: (r) => polygon(3, r * 1.05, -Math.PI / 2),
	pentagon: (r) => polygon(5, r),
	hexagon: (r) => polygon(6, r, 0),
	ellipse: (r) => ellipse(r, r * 0.68),
	rounded_square: (r) => rect(r * 0.85, r * 0.3),
	circle: (r) => ellipse(r, r),
	diamond: (r) => polygon(4, r),
	frame: (r) => rect(r * 0.95, r * 0.08)
};

/** How an edge is stroked. `wavering` is displaced by the filter the glyph defines. */
export const EDGES: Record<string, { dash?: string; join: 'miter' | 'round'; width: number; waver: boolean }> = {
	none: { join: 'miter', width: 3, waver: false },
	straight: { join: 'miter', width: 3, waver: false },
	wavering: { join: 'round', width: 3, waver: true },
	round: { join: 'round', width: 5, waver: false },
	broken: { dash: '7 5', join: 'miter', width: 3, waver: false }
};

/** An exactness class's mark on the outline. */
export const EXACTNESS_MARKS = new Set(['none', 'double_outline', 'source_notch', 'tilde']);

/** How an element's state fills its outline. */
export const FILLS = new Set(['empty', 'partial', 'full', 'hatched']);

/** A state's mark, drawn at the centre. Empty for `none`. */
export const STATE_MARKS: Record<string, string> = {
	none: '',
	dot: 'M50,50 m-5,0 a5,5 0 1 0 10,0 a5,5 0 1 0 -10,0',
	slash: 'M38,64 L62,36',
	person: 'M50,38 m-5,0 a5,5 0 1 0 10,0 a5,5 0 1 0 -10,0 M40,64 Q50,46 60,64',
	pause: 'M44,38 V62 M56,38 V62',
	check: 'M38,51 L47,60 L63,40',
	cross: 'M39,39 L61,61 M61,39 L39,61',
	raised: 'M50,62 V38 M40,48 L50,38 L60,48'
};

/** A motion, as the CSS animation that carries it; `none` carries none. */
export const MOTIONS = new Set(['none', 'pulse', 'shimmer', 'swell']);

/** A motion's still mark: a ring around the outline, drawn when motion is stopped. */
export const STILL_MARKS: Record<string, string | null> = {
	none: null,
	ring_solid: '',
	ring_dotted: '1 4',
	ring_open: '150 60'
};

export function known(token: string, family: Record<string, unknown> | Set<string>): boolean {
	return family instanceof Set ? family.has(token) : Object.hasOwn(family, token);
}
