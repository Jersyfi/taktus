// The words of Today (ADR-0178 §3). The number is the stream's own count of changes delivered
// since the page opened; nothing else is counted here.

/** How many changes arrived since the page opened. */
export function changesLine(changes: number): string {
	if (changes === 0) return 'No change has arrived since you opened this page.';
	return `${changes} ${changes === 1 ? 'change has' : 'changes have'} arrived since you opened this page.`;
}

const NOUN: Record<string, string> = {
	requests: 'decision request',
	needs: 'need',
	autonomy: 'raise of a level',
	findings: 'finding in review'
};

/** What the lines say when none of them waits: only the kinds the surface let the reader read,
 * so that the sentence claims nothing about a kind it did not answer. */
export function nothingWaits(kinds: string[]): string | null {
	const named = kinds.map((k) => NOUN[k]).filter((n): n is string => Boolean(n));
	if (named.length === 0) return null;
	const list = named.length === 1 ? named[0] : `${named.slice(0, -1).join(', ')} or ${named.at(-1)}`;
	return `No ${list} waits for you.`;
}

/** How an area of the overview is headed: by the name the surface hands, and only as a detail by
 * the identifier Taktus generated. An area the surface names only by its identifier is headed
 * in words, never by the raw identifier. */
export function areaTitle(area: { id: string; name: string }): { title: string; detail: string | null } {
	if (area.name && area.name !== area.id) return { title: area.name, detail: area.id };
	return { title: 'Your organisation', detail: area.id };
}
