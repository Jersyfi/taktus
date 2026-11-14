// The one list of the web app's destinations (ADR-0178 §1, ADR-0321 §1). Every width draws this
// list and no other. A band is an order by what the reader is trying to do, never a permission:
// every reader sees every destination, and each page says what the surface lets this reader read.
// A destination marked `more` sits in its band's fold. Pages that answer one question from several
// sides share a destination and carry tabs (`TABS`).

import type { Line } from './governance';
import type { OperationLine } from './operation';

export type Band = 'you' | 'work' | 'steer' | 'depends' | 'running';
export type IconName =
	| 'today'
	| 'decide'
	| 'need'
	| 'yours'
	| 'chat'
	| 'ask'
	| 'processes'
	| 'runs'
	| 'gallery'
	| 'streams'
	| 'discover'
	| 'figures'
	| 'value'
	| 'report'
	| 'levels'
	| 'stages'
	| 'findings'
	| 'trials'
	| 'acts'
	| 'depends'
	| 'privacy'
	| 'incident'
	| 'alert'
	| 'backup'
	| 'signal'
	| 'tenants';

export interface Destination {
	id: string;
	label: string;
	href: string;
	band: Band;
	icon: IconName;
	/** The route ids this destination is current on: the route itself, and those under it. */
	routes: string[];
	/** In the band's fold, one click further. */
	more?: boolean;
}

export const BANDS: { id: Band; label: string }[] = [
	{ id: 'you', label: 'For you' },
	{ id: 'work', label: 'Work' },
	{ id: 'steer', label: 'Steer' },
	{ id: 'depends', label: 'Depends on' },
	{ id: 'running', label: 'Keep running' }
];

export const DESTINATIONS: Destination[] = [
	{ id: 'today', label: 'Today', href: '#/', band: 'you', icon: 'today', routes: ['/', '/waits'] },
	{ id: 'ask', label: 'Ask Taktus', href: '#/ask', band: 'you', icon: 'chat', routes: ['/ask'] },
	{ id: 'requests', label: 'Decisions', href: '#/requests', band: 'you', icon: 'decide', routes: ['/requests', '/reports'] },
	{ id: 'needs', label: 'Needs', href: '#/needs', band: 'you', icon: 'need', routes: ['/needs'] },
	{ id: 'me', label: 'Yours', href: '#/me', band: 'you', icon: 'yours', routes: ['/me'] },
	{ id: 'coach', label: 'Coach', href: '#/coach', band: 'you', icon: 'yours', routes: ['/coach'], more: true },
	{ id: 'proposed', label: 'Proposed', href: '#/proposed', band: 'you', icon: 'discover', routes: ['/proposed'], more: true },
	{ id: 'processes', label: 'Processes', href: '#/processes', band: 'work', icon: 'processes', routes: ['/processes', '/changes', '/variants', '/spend/processes'] },
	{ id: 'runs', label: 'Runs', href: '#/runs', band: 'work', icon: 'runs', routes: ['/runs', '/origins', '/stages', '/spend/runs'] },
	{ id: 'start', label: 'Start work', href: '#/catalogue', band: 'work', icon: 'ask', routes: ['/catalogue', '/gallery', '/plans'] },
	{ id: 'streams', label: 'Streams', href: '#/streams', band: 'work', icon: 'streams', routes: ['/streams'], more: true },
	{ id: 'chains', label: 'Chains', href: '#/chains', band: 'work', icon: 'streams', routes: ['/chains'], more: true },
	{ id: 'discoveries', label: 'Discoveries', href: '#/discoveries', band: 'work', icon: 'discover', routes: ['/discoveries'], more: true },
	{ id: 'autonomy', label: 'Levels', href: '#/autonomy', band: 'steer', icon: 'levels', routes: ['/autonomy'] },
	{ id: 'findings', label: 'Findings', href: '#/findings', band: 'steer', icon: 'findings', routes: ['/findings'] },
	{ id: 'value', label: 'Value and figures', href: '#/value', band: 'steer', icon: 'value', routes: ['/value', '/views', '/role-reports'] },
	{ id: 'trials', label: 'Trials', href: '#/trials', band: 'steer', icon: 'trials', routes: ['/trials'] },
	{ id: 'introduction', label: 'Introduction', href: '#/introduction', band: 'steer', icon: 'stages', routes: ['/introduction'], more: true },
	{ id: 'structure', label: 'Structure', href: '#/structure', band: 'steer', icon: 'streams', routes: ['/structure'], more: true },
	{ id: 'subjects', label: 'Data protection', href: '#/subjects', band: 'steer', icon: 'privacy', routes: ['/subjects'], more: true },
	{ id: 'register', label: 'What acts', href: '#/register', band: 'depends', icon: 'acts', routes: ['/register'] },
	{ id: 'dependencies', label: 'Dependencies', href: '#/dependencies', band: 'depends', icon: 'depends', routes: ['/dependencies'] },
	{ id: 'operation', label: 'Operation', href: '#/incidents', band: 'running', icon: 'signal', routes: ['/incidents', '/alerts', '/backup', '/signals', '/health'] },
	{ id: 'administration', label: 'Administration', href: '#/administration', band: 'running', icon: 'tenants', routes: ['/administration'], more: true },
	{ id: 'tenants', label: 'Tenants', href: '#/tenants', band: 'running', icon: 'tenants', routes: ['/tenants'], more: true }
];

/** The tabs of the destinations that hold several pages (ADR-0321 §1). */
export const TABS: Record<string, { label: string; href: string; route: string }[]> = {
	start: [
		{ label: 'Ask for', href: '#/catalogue', route: '/catalogue' },
		{ label: 'Gallery', href: '#/gallery', route: '/gallery' },
		{ label: 'Plan', href: '#/plans', route: '/plans' }
	],
	value: [
		{ label: 'Value', href: '#/value', route: '/value' },
		{ label: 'Figures', href: '#/views', route: '/views' },
		{ label: 'Reports', href: '#/role-reports', route: '/role-reports' }
	],
	operation: [
		{ label: 'Incidents', href: '#/incidents', route: '/incidents' },
		{ label: 'Alerts', href: '#/alerts', route: '/alerts' },
		{ label: 'Backup', href: '#/backup', route: '/backup' },
		{ label: 'Signals', href: '#/signals', route: '/signals' },
		{ label: 'Health', href: '#/health', route: '/health' }
	]
};

/** What a phone's bottom bar holds (ADR-0321 §4); *Menu* opens the whole list. */
export const BOTTOM: { id: string; label: string; href: string; icon: IconName; routes: string[] }[] = [
	{ id: 'today', label: 'Today', href: '#/', icon: 'today', routes: ['/'] },
	{ id: 'waits', label: 'Waits', href: '#/waits', icon: 'decide', routes: ['/waits'] },
	{ id: 'runs', label: 'Runs', href: '#/runs', icon: 'runs', routes: ['/runs'] }
];

function routeMatches(route: string, routeId: string): boolean {
	return route === '/' ? routeId === '/' : routeId === route || routeId.startsWith(`${route}/`);
}

/** The destination a route belongs to: the longest route prefix that names it. */
export function currentDestination(routeId: string | null | undefined): string | null {
	if (!routeId) return null;
	let best: { id: string; length: number } | null = null;
	for (const d of DESTINATIONS) {
		for (const r of d.routes) {
			if (routeMatches(r, routeId) && (!best || r.length > best.length)) best = { id: d.id, length: r.length };
		}
	}
	return best?.id ?? null;
}

/** The item of the bottom bar a route belongs to, if any. */
export function currentBottom(routeId: string | null | undefined): string | null {
	if (!routeId) return null;
	return BOTTOM.find((b) => b.routes.some((r) => routeMatches(r, routeId)))?.id ?? null;
}

/** The governance kinds and the operation kinds, as the destination each one leads to. */
const OF_LINE: Record<Line['kind'] | OperationLine['kind'], string> = {
	requests: 'requests',
	needs: 'needs',
	autonomy: 'autonomy',
	findings: 'findings',
	tenants: 'tenants',
	incidents: 'operation',
	alerts: 'operation',
	backup: 'operation',
	signals: 'operation'
};

/** The destinations that wait for the reader, from the lines the surface answered (ADR-0178 §2).
 * A kind the surface refused has no line, and so no mark. Nothing is counted here. */
export function waitingDestinations(governs: Line[], operation: OperationLine[]): Set<string> {
	const waiting = new Set<string>();
	for (const line of governs) if (line.waiting) waiting.add(OF_LINE[line.kind]);
	for (const line of operation) if (line.red) waiting.add(OF_LINE[line.kind]);
	return waiting;
}

/** A mark the surface named by its kind, as the destination it leads to; a destination id is
 * kept as it is. */
export function markOf(kind: string): string {
	return (OF_LINE as Record<string, string>)[kind] ?? kind;
}

/** The trail from the lists to where the reader stands (ADR-0321 §3): every step but the last a
 * link. */
export function trail(routeId: string | null | undefined, params: Record<string, string | undefined>): { label: string; href?: string }[] {
	if (!routeId) return [];
	const run = params['id'] ?? params['run'];
	if (routeId.startsWith('/processes/')) {
		return [{ label: 'Processes', href: '#/processes' }, { label: params['id'] ?? '' }];
	}
	if (routeId.startsWith('/runs/') && run) {
		return [{ label: 'Runs', href: '#/runs' }, { label: `Run ${run}` }];
	}
	if (routeId.startsWith('/origins/') && params['run']) {
		return [
			{ label: 'Runs', href: '#/runs' },
			{ label: `Run ${params['run']}`, href: `#/runs/${encodeURIComponent(params['run'])}` },
			{ label: `Origin of ${params['step'] ?? ''}` }
		];
	}
	if (routeId.startsWith('/stages/') && run) {
		return [
			{ label: 'Runs', href: '#/runs' },
			{ label: `Run ${run}`, href: `#/runs/${encodeURIComponent(run)}` },
			{ label: 'Stages' }
		];
	}
	return [];
}
