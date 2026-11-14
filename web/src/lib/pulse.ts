// The one stream of the tenant's changes the frame holds (ADR-0323 §1). Every page listens to it
// instead of opening its own: the mark in the bar beats on it, Today's strip and list are drawn
// from it, and a level page reads its level again when a change concerns it.
//
// It asks for the snapshot's position only (`snapshot=position`). A surface that does not know
// the parameter sends every run with it; nothing here reads them.

import { follow, type StreamEvent } from './stream';
import type { Change } from './types';

/** How many changes the frame keeps for the open visit. */
export const KEPT_CHANGES = 200;

export type Listener = (event: StreamEvent) => void;

/** Where a stream stands: not opened, connected, reconnecting, or refused by the surface. */
export type Standing = 'idle' | 'live' | 'reconnecting' | 'refused';

export interface PulseOptions {
	fetcher?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
}

export class TenantStream {
	standing: Standing = 'idle';
	/** The changes delivered since the stream opened. */
	count = 0;
	/** The newest changes, newest last; at most `KEPT_CHANGES`. */
	recent: Change[] = [];

	private listeners = new Set<Listener>();
	private watchers = new Set<() => void>();
	private controller: AbortController | null = null;

	/** Listens to every event; the snapshot of a reconnect included. Returns the way to stop. */
	subscribe(listener: Listener): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}

	/** Told whenever the standing, the count or the kept changes moved. */
	watch(watcher: () => void): () => void {
		this.watchers.add(watcher);
		return () => this.watchers.delete(watcher);
	}

	/** Opens the stream, once. A stream already open, or connecting, is kept. */
	open(base: URL, options: PulseOptions = {}): Promise<void> {
		if (this.controller && !this.controller.signal.aborted) return Promise.resolve();
		const controller = new AbortController();
		this.controller = controller;
		const url = new URL('changes', base);
		url.searchParams.set('snapshot', 'position');
		return follow({
			url,
			signal: controller.signal,
			...(options.fetcher ? { fetcher: options.fetcher } : {}),
			...(options.sleep ? { sleep: options.sleep } : {}),
			onConnected: (open) => this.stand(open ? 'live' : 'reconnecting'),
			onEvent: (event) => {
				if (event.kind === 'change') {
					this.count += 1;
					this.recent = [...this.recent, event.change].slice(-KEPT_CHANGES);
				}
				this.told();
				for (const listener of this.listeners) listener(event);
			}
		}).then((ended) => {
			if (ended.reason === 'refused') this.stand('refused');
			if (this.controller === controller) this.controller = null;
		});
	}

	/** Closes the stream: the reader signed out, or the surface refused. */
	close(): void {
		this.controller?.abort();
		this.controller = null;
		this.stand('idle');
	}

	private stand(standing: Standing): void {
		this.standing = standing;
		this.told();
	}

	private told(): void {
		for (const watcher of this.watchers) watcher();
	}
}
