<!--
	How a process really runs: `GET /processes/{id}/variants` (ADR-0147 §4).
-->
<script lang="ts">
	import { page } from '$app/state';
	import { variantsPath, type VariantsView as Variants } from '../../../lib/acting';
	import Reading from '../../../lib/Reading.svelte';
	import VariantsView from '../../../lib/VariantsView.svelte';

	const path = $derived(variantsPath(page.params.id ?? ''));
</script>

<Reading {path} reading="Reading how it runs…">
	{#snippet children(view: Variants)}
		<VariantsView {view} />
	{/snippet}
</Reading>
