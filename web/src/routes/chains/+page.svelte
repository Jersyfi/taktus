<!--
	End-to-end chains across domains: `GET /chains` (UC-15.4, ADR-0301 §4).
-->
<script lang="ts">
	import ChainsView from '../../lib/ChainsView.svelte';
	import Reading from '../../lib/Reading.svelte';
	import { CHAINS, type ChainList } from '../../lib/chains';
</script>

<Reading path={CHAINS} reading="Reading the chains…">
	{#snippet children(view: ChainList)}
		<ChainsView {view} />
	{/snippet}
</Reading>
