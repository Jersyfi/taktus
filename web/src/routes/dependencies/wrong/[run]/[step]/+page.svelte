<!--
	Where a wrong result went: `GET /dependencies/wrong-result/{run}/{step}` (ADR-0147 §3,
	UC-4.11's counts).
-->
<script lang="ts">
	import { page } from '$app/state';
	import { wrongResultPath, type WrongResultView } from '../../../../../lib/acting';
	import DependenciesView from '../../../../../lib/DependenciesView.svelte';
	import Reading from '../../../../../lib/Reading.svelte';

	const path = $derived(wrongResultPath(page.params.run ?? '', page.params.step ?? ''));
</script>

<Reading {path} reading="Following the result…">
	{#snippet children(wrong: WrongResultView)}
		<DependenciesView {wrong} />
	{/snippet}
</Reading>
