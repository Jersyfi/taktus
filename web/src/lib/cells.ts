// How each token of the visual vocabulary becomes pixels (ADR-0059: the representation turns
// tokens into pixels and chooses no token itself). Every step is drawn as a cell (DEC-0185):
// its membrane is its family, its nucleus its method kind, rings its exactness class, its
// cytoplasm and a badge its state. Every token the vocabulary names has its drawing here; a test
// fails a token that has none. A family's hue is added on top (M1.20); every distinction is
// already carried without it.

const C = 50;
/** The membrane's radius, in a box of 100. */
export const R = 33;

/** A circle as a path. */
export function circle(r: number): string {
	return `M${C - r},${C} a${r},${r} 0 1 0 ${2 * r},0 a${r},${r} 0 1 0 ${-2 * r},0 Z`;
}

/** A smooth closed curve through points (Catmull-Rom as cubic Béziers). */
function smooth(points: [number, number][]): string {
	const n = points.length;
	const f = (v: number) => v.toFixed(2);
	let d = `M${f(points[0]![0])},${f(points[0]![1])}`;
	for (let i = 0; i < n; i += 1) {
		const p0 = points[(i - 1 + n) % n]!;
		const p1 = points[i]!;
		const p2 = points[(i + 1) % n]!;
		const p3 = points[(i + 2) % n]!;
		const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
		const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
		d += ` C${f(c1[0]!)},${f(c1[1]!)} ${f(c2[0]!)},${f(c2[1]!)} ${f(p2[0])},${f(p2[1])}`;
	}
	return `${d} Z`;
}

const WOBBLE = [0.07, -0.05, 0.09, -0.02, 0.05, -0.08, 0.03, 0.08, -0.06];

/** A fluid membrane, one of three shapes it passes through while it works. */
export function fluid(phase: number): string {
	const points: [number, number][] = [];
	for (let i = 0; i < 9; i += 1) {
		const a = (i / 9) * Math.PI * 2;
		const k = 1 + WOBBLE[(i + phase * 3) % WOBBLE.length]!;
		points.push([C + R * k * Math.cos(a), C + R * k * Math.sin(a)]);
	}
	return smooth(points);
}

/** The beads of a reproducible membrane: evenly spaced, the same every time. */
export function beads(count: number): [number, number][] {
	return Array.from({ length: count }, (_, i) => {
		const a = (i / count) * Math.PI * 2;
		return [C + R * Math.cos(a), C + R * Math.sin(a)] as [number, number];
	});
}

/** A step's membrane by its family, and the membrane of every other element. */
export const MEMBRANES = new Set(['beaded', 'fluid', 'soft', 'dormant', 'tissue', 'crystal', 'root', 'signal']);

/** The hue a membrane takes on top of its form: the family's, or the ink's. */
export const HUES: Record<string, string> = {
	beaded: 'var(--reproducible)',
	fluid: 'var(--variable)',
	soft: 'var(--person)',
	dormant: 'var(--waiting)',
	tissue: 'var(--ink-2)',
	crystal: 'var(--ink)',
	root: 'var(--ink-2)',
	signal: 'var(--ink-2)'
};

/** A nucleus, as a list of drawn parts in a box of 100: one per method kind. */
export type Part =
	| { dot: [number, number, number] }
	| { ring: [number, number, number, number] }
	| { line: [number, number, number, number] }
	| { cloud: number };

function at(angle: number, r: number): [number, number] {
	return [C + r * Math.cos(angle), C + r * Math.sin(angle)];
}

export const NUCLEI: Record<string, Part[]> = {
	none: [],
	single: [{ dot: [C, C, 8] }],
	population: [
		[0, 0],
		[9, 0],
		[-9, 0],
		[4.5, 7.8],
		[-4.5, 7.8],
		[4.5, -7.8],
		[-4.5, -7.8]
	].map(([x, y]) => ({ dot: [C + x!, C + y!, 2.6] as [number, number, number] })),
	cluster: (() => {
		const p = [at(-Math.PI / 2, 8), at(Math.PI / 6, 8), at((5 * Math.PI) / 6, 8)];
		return [
			{ line: [...p[0]!, ...p[1]!] as [number, number, number, number] },
			{ line: [...p[1]!, ...p[2]!] as [number, number, number, number] },
			{ line: [...p[2]!, ...p[0]!] as [number, number, number, number] },
			...p.map(([x, y]) => ({ dot: [x, y, 4.4] as [number, number, number] }))
		];
	})(),
	network: [
		...Array.from({ length: 6 }, (_, i) => {
			const [x, y] = at((i / 6) * Math.PI * 2 - Math.PI / 2, 12);
			return [
				{ line: [C, C, x, y] as [number, number, number, number] },
				{ dot: [x, y, 2.6] as [number, number, number] }
			];
		}).flat(),
		{ dot: [C, C, 4] }
	],
	cloud: [{ cloud: 15 }, { dot: [C, C, 3.6] }],
	satellites: [{ dot: [C, C, 6.5] }, ...[-0.5, 1.6, 3.4].map((a) => ({ dot: [...at(a, 14), 2.4] as [number, number, number] }))],
	open: [{ ring: [C, C, 8.5, 3.4] }],
	seed: [{ dot: [C, C, 3.2] }]
};

/** An exactness class's rings on the membrane. */
export const RINGS = new Set(['none', 'inner_membrane', 'pore', 'tolerance_band']);

/** How an element's state fills its membrane: the cytoplasm's density. */
export const FILLS: Record<string, number> = { empty: 0, partial: 0.16, full: 0.34, hatched: 0 };

/** A state's badge, drawn on the membrane at half past four, in a box of 12 around its centre. */
export const STATE_MARKS: Record<string, string> = {
	none: '',
	dot: 'M0,0 m-2.2,0 a2.2,2.2 0 1 0 4.4,0 a2.2,2.2 0 1 0 -4.4,0',
	slash: 'M-3.6,3.6 L3.6,-3.6',
	person: 'M0,0 m-3.2,0 a3.2,3.2 0 1 0 6.4,0 a3.2,3.2 0 1 0 -6.4,0',
	pause: 'M-1.8,-3.4 V3.4 M1.8,-3.4 V3.4',
	check: 'M-3.4,0.2 L-1,2.8 L3.6,-2.6',
	cross: 'M-3,-3 L3,3 M3,-3 L-3,3',
	raised: 'M0,3.6 V-3.4 M-3,-0.6 L0,-3.6 L3,-0.6',
	question: 'M-2.4,-1.6 Q-2.4,-4 0,-4 Q2.6,-4 2.6,-1.8 Q2.6,0 0,0.6 V1.4 M0,3.4 V3.6',
	quote: 'M-2.2,-2.6 V0.4 M2.2,-2.6 V0.4'
};

/** A motion, as the animation that carries it; `none` carries none. */
export const MOTIONS = new Set(['none', 'pulse', 'shimmer', 'swell']);

/** How long one cycle of a motion lasts, in seconds. Every reproducible cell beats in phase. */
export const PERIODS: Record<string, number> = { pulse: 1.2, shimmer: 3.1, swell: 4.2 };

/** A motion's still mark: an aura around the membrane, drawn when motion is stopped. */
export const STILL_MARKS: Record<string, string | null> = {
	none: null,
	aura_solid: '',
	aura_dotted: '0.5 5',
	aura_open: '190 106'
};

export function known(token: string, family: Record<string, unknown> | Set<string>): boolean {
	return family instanceof Set ? family.has(token) : Object.hasOwn(family, token);
}
