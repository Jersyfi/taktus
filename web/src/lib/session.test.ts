// The reader's sign-in (ADR-0119): the key is sent once, in the header, and kept nowhere.

import { afterEach, describe, expect, it } from 'vitest';
import { forgetOldKey, signIn, signOut } from './session';

class MemoryStorage implements Storage {
	private items = new Map<string, string>();
	get length() {
		return this.items.size;
	}
	clear() {
		this.items.clear();
	}
	getItem(name: string) {
		return this.items.get(name) ?? null;
	}
	key(index: number) {
		return [...this.items.keys()][index] ?? null;
	}
	removeItem(name: string) {
		this.items.delete(name);
	}
	setItem(name: string, value: string) {
		this.items.set(name, value);
	}
}

// A placeholder in the shape of an account key, built so that no scanner takes it for one.
const KEY = ['tka', 'placeholder'].join('_');
const scope = globalThis as unknown as { localStorage?: Storage; sessionStorage?: Storage };

afterEach(() => {
	delete scope.localStorage;
	delete scope.sessionStorage;
});

/** Every source of the app, as text: the library and the pages, without the tests. */
const SOURCES = import.meta.glob(['../**/*.ts', '../**/*.svelte', '!../**/*.test.ts'], {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

describe('signing in', () => {
	it('sends the key once, in the header, and keeps it nowhere', async () => {
		scope.localStorage = new MemoryStorage();
		scope.sessionStorage = new MemoryStorage();
		const calls: { url: string; init: RequestInit }[] = [];
		const fetcher = (async (url: URL, init: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(JSON.stringify({ tenant: 't', identity: 'idn_ada', expires_at: '2026-10-23T00:00:00Z' }), {
				status: 201
			});
		}) as unknown as typeof fetch;
		const answer = await signIn(new URL('https://instance.test/p/'), ` ${KEY} `, fetcher);
		expect(answer).toEqual({ ok: true, identity: 'idn_ada', expiresAt: '2026-10-23T00:00:00Z' });
		expect(calls).toHaveLength(1);
		expect(calls[0]!.url).toBe('https://instance.test/p/session');
		expect(calls[0]!.url).not.toContain(KEY);
		expect(calls[0]!.init.method).toBe('POST');
		expect(calls[0]!.init.credentials).toBe('same-origin');
		expect(calls[0]!.init.body).toBeUndefined();
		expect((calls[0]!.init.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${KEY}`);
		expect(scope.localStorage.length).toBe(0);
		expect(scope.sessionStorage.length).toBe(0);
	});

	it('says when the instance refused the key', async () => {
		const fetcher = (async () => new Response(null, { status: 401, statusText: 'Unauthorized' })) as unknown as typeof fetch;
		const answer = await signIn(new URL('https://instance.test/'), KEY, fetcher);
		expect(answer.ok).toBe(false);
	});

	it('signs out with the cookie, sending no key', async () => {
		const calls: { url: string; init: RequestInit }[] = [];
		const fetcher = (async (url: URL, init: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(null, { status: 204 });
		}) as unknown as typeof fetch;
		await signOut(new URL('https://instance.test/p/'), fetcher);
		expect(calls[0]!.url).toBe('https://instance.test/p/session');
		expect(calls[0]!.init.method).toBe('DELETE');
		expect(calls[0]!.init.credentials).toBe('same-origin');
		expect(calls[0]!.init.headers).toBeUndefined();
	});

	it('removes a key an earlier version kept for the tab', () => {
		const storage = new MemoryStorage();
		storage.setItem('taktus.key', KEY);
		forgetOldKey(storage);
		expect(storage.getItem('taktus.key')).toBeNull();
	});

	it('keeps no account key in web storage anywhere in the app', () => {
		expect(Object.keys(SOURCES).length).toBeGreaterThan(10);
		const lasting = Object.entries(SOURCES)
			.filter(([, text]) => /localStorage|indexedDB|document\.cookie/.test(text))
			.map(([path]) => path);
		expect(lasting).toEqual([]);
		// The one write to the tab's storage is the instance's administration key, which is no
		// account key and is kept for the tab only (ADR-0104, ADR-0122).
		const writers = Object.entries(SOURCES)
			.filter(([, text]) => /\.setItem\(/.test(text))
			.map(([path]) => path);
		expect(writers).toEqual(['./governance.ts']);
		expect(SOURCES['./governance.ts']).toMatch(/setItem\(ADMINISTRATION,/);
		expect((SOURCES['./governance.ts']!.match(/\.setItem\(/g) ?? []).length).toBe(1);
	});
});
