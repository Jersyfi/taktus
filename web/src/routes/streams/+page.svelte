<!--
	The organisation seen as value streams: `GET /streams` (UC-15.6, ADR-0159 §5).
-->
<script lang="ts">
	import Reading from '../../lib/Reading.svelte';
	import StreamsView from '../../lib/StreamsView.svelte';
	import { STREAMS, type StreamMap } from '../../lib/views';
</script>

<Reading path={STREAMS} reading="Reading the value streams…">
	{#snippet children(view: StreamMap)}
		<StreamsView {view} />
	{/snippet}
</Reading>
