// The words of Today (ADR-0322 §4). Every number is one the surface counted; a count it did not
// make is left out, never said as zero.

import type { Counts } from './todayData';

/** What the first tile of the pulse card says under its figure. */
export function waitsLine(count: number | null): string {
	if (count === null) return 'waits could not be read';
	if (count === 0) return 'nothing waits for you';
	return count === 1 ? 'waits for you' : 'wait for you';
}

export interface Tile {
	key: keyof Counts;
	value: number;
	label: string;
	href: string;
	/** Something is wrong: drawn with a border of the alert family, said in its label. */
	alert: boolean;
}

const TILES: { key: keyof Counts; one: string; many: string; href: string; alerting: boolean }[] = [
	{ key: 'running', one: 'run working now', many: 'runs working now', href: '#/runs?state=running', alerting: false },
	{ key: 'waiting_on_person', one: 'run waiting on a person', many: 'runs waiting on a person', href: '#/runs?state=waiting_human', alerting: false },
	{ key: 'failed_24h', one: 'failure in 24 hours', many: 'failures in 24 hours', href: '#/runs?state=escalated', alerting: true },
	{ key: 'incidents', one: 'incident open', many: 'incidents open', href: '#/incidents', alerting: true },
	{ key: 'alerts', one: 'alert in effect', many: 'alerts in effect', href: '#/alerts', alerting: true }
];

/** The glance strip: one tile per count the surface made, in a fixed order. */
export function glance(counts: Counts): Tile[] {
	return TILES.flatMap((t) => {
		const value = counts[t.key];
		if (value === null) return [];
		return [{ key: t.key, value, label: value === 1 ? t.one : t.many, href: t.href, alert: t.alerting && value > 0 }];
	});
}

/** How an area of the overview is headed: by the name the surface hands, and only as a detail by
 * the identifier Taktus generated. An area the surface names only by its identifier is headed
 * in words, never by the raw identifier. */
export function areaTitle(area: { id: string; name: string }): { title: string; detail: string | null } {
	if (area.name && area.name !== area.id) return { title: area.name, detail: area.id };
	return { title: 'Your organisation', detail: area.id };
}
