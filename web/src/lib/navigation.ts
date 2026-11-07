// The one list of the web app's destinations (ADR-0178 §1). Every width draws this list and no
// other. A band is an order by what the reader is trying to do, never a permission: every reader
// sees every destination, and each page says what the surface lets this reader read.

import type { Line } from './governance';
import type { OperationLine } from './operation';

export type Band = 'now' | 'start' | 'steer' | 'running';
export type IconName =
	| 'today'
	| 'decide'
	| 'need'
	| 'yours'
	| 'ask'
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
}

export const BANDS: { id: Band; label: string }[] = [
	{ id: 'now', label: 'Now' },
	{ id: 'start', label: 'Start work' },
	{ id: 'steer', label: 'Steer' },
	{ id: 'running', label: 'Keep running' }
];

export const DESTINATIONS: Destination[] = [
	{ id: 'today', label: 'Today', href: '#/', band: 'now', icon: 'today', routes: ['/', '/processes', '/runs', '/origins', '/stages', '/changes', '/variants', '/spend', '/reports'] },
	{ id: 'requests', label: 'Decisions', href: '#/requests', band: 'now', icon: 'decide', routes: ['/requests'] },
	{ id: 'needs', label: 'Needs', href: '#/needs', band: 'now', icon: 'need', routes: ['/needs'] },
	{ id: 'me', label: 'Yours', href: '#/me', band: 'now', icon: 'yours', routes: ['/me'] },
	{ id: 'catalogue', label: 'Ask for', href: '#/catalogue', band: 'start', icon: 'ask', routes: ['/catalogue'] },
	{ id: 'gallery', label: 'Gallery', href: '#/gallery', band: 'start', icon: 'gallery', routes: ['/gallery'] },
	{ id: 'streams', label: 'Streams', href: '#/streams', band: 'start', icon: 'streams', routes: ['/streams'] },
	{ id: 'discoveries', label: 'Discoveries', href: '#/discoveries', band: 'start', icon: 'discover', routes: ['/discoveries'] },
	{ id: 'views', label: 'Figures', href: '#/views', band: 'steer', icon: 'figures', routes: ['/views'] },
	{ id: 'value', label: 'Value', href: '#/value', band: 'steer', icon: 'value', routes: ['/value'] },
	{ id: 'role-reports', label: 'Reports', href: '#/role-reports', band: 'steer', icon: 'report', routes: ['/role-reports'] },
	{ id: 'autonomy', label: 'Levels', href: '#/autonomy', band: 'steer', icon: 'levels', routes: ['/autonomy'] },
	{ id: 'introduction', label: 'Introduction', href: '#/introduction', band: 'steer', icon: 'stages', routes: ['/introduction'] },
	{ id: 'findings', label: 'Findings', href: '#/findings', band: 'steer', icon: 'findings', routes: ['/findings'] },
	{ id: 'trials', label: 'Trials', href: '#/trials', band: 'steer', icon: 'trials', routes: ['/trials'] },
	{ id: 'register', label: 'What acts', href: '#/register', band: 'steer', icon: 'acts', routes: ['/register'] },
	{ id: 'dependencies', label: 'Dependencies', href: '#/dependencies', band: 'steer', icon: 'depends', routes: ['/dependencies'] },
	{ id: 'subjects', label: 'Data protection', href: '#/subjects', band: 'steer', icon: 'privacy', routes: ['/subjects'] },
	{ id: 'incidents', label: 'Incidents', href: '#/incidents', band: 'running', icon: 'incident', routes: ['/incidents'] },
	{ id: 'alerts', label: 'Alerts', href: '#/alerts', band: 'running', icon: 'alert', routes: ['/alerts'] },
	{ id: 'backup', label: 'Backup', href: '#/backup', band: 'running', icon: 'backup', routes: ['/backup'] },
	{ id: 'signals', label: 'Signals', href: '#/signals', band: 'running', icon: 'signal', routes: ['/signals'] },
	{ id: 'tenants', label: 'Tenants', href: '#/tenants', band: 'running', icon: 'tenants', routes: ['/tenants'] }
];

/** The destination a route belongs to: the longest route prefix that names it. */
export function currentDestination(routeId: string | null | undefined): string | null {
	if (!routeId) return null;
	let best: { id: string; length: number } | null = null;
	for (const d of DESTINATIONS) {
		for (const r of d.routes) {
			const matches = r === '/' ? routeId === '/' : routeId === r || routeId.startsWith(`${r}/`);
			if (matches && (!best || r.length > best.length)) best = { id: d.id, length: r.length };
		}
	}
	return best?.id ?? null;
}

/** The governance kinds and the operation kinds, as the destination each one leads to. */
const OF_LINE: Record<Line['kind'] | OperationLine['kind'], string> = {
	requests: 'requests',
	needs: 'needs',
	autonomy: 'autonomy',
	findings: 'findings',
	tenants: 'tenants',
	incidents: 'incidents',
	alerts: 'alerts',
	backup: 'backup',
	signals: 'signals'
};

/** The destinations that wait for the reader, from the lines the surface answered (ADR-0178 §2).
 * A kind the surface refused has no line, and so no mark. Nothing is counted here. */
export function waitingDestinations(governs: Line[], operation: OperationLine[]): Set<string> {
	const waiting = new Set<string>();
	for (const line of governs) if (line.waiting) waiting.add(OF_LINE[line.kind]);
	for (const line of operation) if (line.red) waiting.add(OF_LINE[line.kind]);
	return waiting;
}
