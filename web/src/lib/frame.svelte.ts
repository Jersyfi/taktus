// What the frame shows about the system on every page (ADR-0323): the one stream of the tenant's
// changes, whether it is connected, how many changes it delivered since the frame opened, and
// the newest of them. The mark in the bar beats on it; Today draws its strip and its list from it;
// a level page reads its level again when a change concerns it.

import { forgetShared } from './shared';
import { TenantStream, type Listener, type PulseOptions, type Standing } from './pulse';
import type { Change } from './types';

class Frame {
	readonly stream = new TenantStream();
	/** Where the stream stands; `idle` before the frame opened it. */
	standing: Standing = $state('idle');
	/** The changes delivered since the frame opened. */
	changes = $state(0);
	/** The newest changes, newest last. */
	recent: Change[] = $state([]);

	constructor() {
		this.stream.watch(() => {
			this.standing = this.stream.standing;
			this.changes = this.stream.count;
			this.recent = this.stream.recent;
		});
		// Any change can make a kept read old.
		this.stream.subscribe((event) => {
			if (event.kind === 'change') forgetShared();
		});
	}

	/** null while no stream is open; otherwise whether it is connected. */
	get live(): boolean | null {
		return this.standing === 'idle' || this.standing === 'refused' ? null : this.standing === 'live';
	}

	open(base: URL, options?: PulseOptions): void {
		void this.stream.open(base, options);
	}

	/** Opens the stream again, after the reader signed in. */
	reopen(base: URL): void {
		this.stream.close();
		forgetShared();
		this.open(base);
	}

	subscribe(listener: Listener): () => void {
		return this.stream.subscribe(listener);
	}
}

export const frame = new Frame();
