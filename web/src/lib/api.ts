// How the web app reaches the control plane's surface (ADR-0063).
//
// The app is served at `{prefix}/app/`, and the prefix is the instance's, not the build's.
// The surface is therefore the directory above the app's own, read from the page's address.
// The reader is proved by the session cookie the browser sends with every request to the
// instance (ADR-0119). The page holds no key and sends none.

import type { Problem } from './types';

/** The base URL of the surface, from the address the app was loaded from. */
export function surface(href: string): URL {
	const page = new URL(href);
	page.hash = '';
	page.search = '';
	return new URL('../', page);
}

export type Answer<T> = { ok: true; body: T } | { ok: false; problem: Problem };

async function answered<T>(response: Response): Promise<Answer<T>> {
	if (response.ok) return { ok: true, body: (await response.json()) as T };
	let problem: Problem = { status: response.status, title: response.statusText, detail: '' };
	try {
		problem = { ...problem, ...((await response.json()) as Partial<Problem>) };
	} catch {
		// A body that is no problem document: the status says enough.
	}
	return { ok: false, problem };
}

/** A JSON read as the signed-in reader. A refusal is the surface's problem, never thrown. */
export async function read<T>(base: URL, path: string, fetcher: typeof fetch = fetch): Promise<Answer<T>> {
	const response = await fetcher(new URL(path, base), {
		credentials: 'same-origin',
		headers: { Accept: 'application/json' }
	});
	return answered<T>(response);
}

/** A JSON read with a key other than the reader's sign-in: the instance's administration key,
 * which a page asks for and keeps for its tab (ADR-0104, ADR-0122). It travels in
 * `Authorization: Bearer`, and the surface then reads no cookie (ADR-0119 §3). */
export async function readAs<T>(
	base: URL,
	path: string,
	key: string,
	fetcher: typeof fetch = fetch
): Promise<Answer<T>> {
	const response = await fetcher(new URL(path, base), {
		credentials: 'same-origin',
		headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' }
	});
	return answered<T>(response);
}

/** A JSON write as the signed-in reader: an answer to a decision request, or its confirmation.
 * A refusal is the surface's problem, never thrown. */
export async function send<T>(
	base: URL,
	path: string,
	body: unknown,
	fetcher: typeof fetch = fetch
): Promise<Answer<T>> {
	const response = await fetcher(new URL(path, base), {
		method: 'POST',
		credentials: 'same-origin',
		headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	return answered<T>(response);
}

/** A delete as the signed-in reader: a share withdrawn. A refusal is the surface's problem,
 * never thrown. */
export async function remove<T>(base: URL, path: string, fetcher: typeof fetch = fetch): Promise<Answer<T>> {
	const response = await fetcher(new URL(path, base), {
		method: 'DELETE',
		credentials: 'same-origin',
		headers: { Accept: 'application/json' }
	});
	return answered<T>(response);
}
