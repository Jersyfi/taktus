<!--
	A line icon of the frame (ADR-0178), in a box of 24, drawn in the text's own colour. It says
	nothing alone: a label always stands beside it, so it is hidden from assistive technology.
-->
<script lang="ts">
	import type { IconName } from './navigation';

	type Name = IconName | 'menu' | 'close' | 'motion' | 'leave' | 'sun' | 'moon' | 'system';
	let { name, size = 20 }: { name: Name; size?: number } = $props();

	const PATHS: Record<Name, string> = {
		today: 'M12 3v2M12 19v2M3 12h2M19 12h2M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
		decide: 'M4 5h16v11H9l-5 4V5ZM8.5 10.5l2 2 4-4',
		need: 'M12 3l9 16H3L12 3ZM12 10v4M12 17v.5',
		yours: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21c1.5-4 4.5-6 8-6s6.5 2 8 6',
		ask: 'M5 12h11M12 6l6 6-6 6',
		gallery: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
		streams: 'M3 7c4 0 4 4 9 4s5-4 9-4M3 17c4 0 4-4 9-4s5 4 9 4',
		discover: 'M4 12h3M17 12h3M12 4v3M12 17v3M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
		figures: 'M4 20h16M6 16v-4M10 16V8M14 16v-6M18 16V5',
		value: 'M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3ZM12 8v8M9 12h6',
		report: 'M6 3h9l4 4v14H6V3ZM14 3v5h5M9 12h7M9 16h7',
		levels: 'M5 20V14M10 20V10M15 20V7M20 20V4',
		stages: 'M3 20h5v-5h5v-5h5V5h3',
		findings: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM16 16l5 5',
		trials: 'M9 3h6M10 3v6L5 19a1.5 1.5 0 0 0 1.3 2h11.4a1.5 1.5 0 0 0 1.3-2L14 9V3',
		acts: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
		privacy: 'M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3ZM9 12l2 2 4-4',
		depends: 'M6 6a2 2 0 1 0 0 .1M18 6a2 2 0 1 0 0 .1M12 18a2 2 0 1 0 0 .1M6 8l5 8M18 8l-5 8',
		incident: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5L12 3Z',
		alert: 'M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2ZM10 21h4',
		backup: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3ZM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
		signal: 'M3 12h4l3-7 4 14 3-7h4',
		tenants: 'M3 21V8l6-4 6 4v13M15 11h6v10M7 12h4M7 16h4',
		menu: 'M4 7h16M4 12h16M4 17h16',
		close: 'M6 6l12 12M18 6L6 18',
		motion: 'M8 5v14M16 5v14',
		leave: 'M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10',
		sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5',
		moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z',
		system: 'M3 5h18v11H3zM8 20h8M12 16v4'
	};
</script>

<svg class="icon" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false">
	<path d={PATHS[name]} />
</svg>

<style>
	.icon {
		flex: none;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.7;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
</style>
