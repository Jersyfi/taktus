<!--
	One value stream as role swimlanes: `GET /streams/{stream}` (UC-15.6, ADR-0159 §6).
-->
<script lang="ts">
	import { page } from '$app/state';
	import Reading from '../../../lib/Reading.svelte';
	import StreamLanesView from '../../../lib/StreamLanesView.svelte';
	import { streamPath, type StreamLanes } from '../../../lib/views';

	const path = $derived(streamPath(page.params.id ?? ''));
</script>

<Reading {path} reading="Reading the stream…">
	{#snippet children(view: StreamLanes)}
		<StreamLanesView {view} />
	{/snippet}
</Reading>
