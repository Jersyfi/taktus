<!--
	Where data goes: `GET /dependencies/residency` (ADR-0147 §3). Each adapter leads to what
	depends on it.
-->
<script lang="ts">
	import { RESIDENCY, type ResidencyView } from '../../lib/acting';
	import DependenciesView from '../../lib/DependenciesView.svelte';
	import Reading from '../../lib/Reading.svelte';
</script>

<Reading path={RESIDENCY} reading="Reading where data goes…">
	{#snippet children(residency: ResidencyView)}
		<DependenciesView {residency} />
	{/snippet}
</Reading>
