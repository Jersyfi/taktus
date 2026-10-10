// How the web app reaches the control plane's surface (ADR-0063).
//
// The app is served at `{prefix}/app/`, and the prefix is the instance's, not the build's.
// The surface is therefore the directory above the app's own, read from the page's address.
// The account key travels in `Authorization: Bearer` and nowhere else (ADR-0055 §1).

import type { Problem } from './types';

/** The base URL of the surface, from the address the app was loaded from. */
export function surface(href: string): URL {
	const page = new URL(href);
	page.hash = '';
	page.search = '';
	return new URL('../', page);
}

export type Answer<T> = { ok: true; body: T } | { ok: false; problem: Problem };

/** A JSON read with the reader's key. A refusal is the surface's problem, never thrown. */
export async function read<T>(
	base: URL,
	path: string,
	key: string,
	fetcher: typeof fetch = fetch
): Promise<Answer<T>> {
	const response = await fetcher(new URL(path, base), {
		headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' }
	});
	if (response.ok) return { ok: true, body: (await response.json()) as T };
	let problem: Problem = { status: response.status, title: response.statusText, detail: '' };
	try {
		problem = { ...problem, ...((await response.json()) as Partial<Problem>) };
	} catch {
		// A body that is no problem document: the status says enough.
	}
	return { ok: false, problem };
}
