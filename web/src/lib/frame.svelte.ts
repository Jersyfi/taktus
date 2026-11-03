// What the frame shows about the page it holds (ADR-0178): whether the page follows a stream and
// is connected, and how many changes that stream delivered since the page opened. A page that
// follows nothing leaves `live` at null, and the frame then shows no live state at all.

class Frame {
	/** null: the page follows no stream; otherwise whether its stream is connected. */
	live: boolean | null = $state(null);
	/** The changes the page's stream delivered since it opened. */
	changes = $state(0);

	follow(): void {
		this.live = false;
		this.changes = 0;
	}

	connected(open: boolean): void {
		this.live = open;
	}

	changed(): void {
		this.changes += 1;
	}

	leave(): void {
		this.live = null;
		this.changes = 0;
	}
}

export const frame = new Frame();
