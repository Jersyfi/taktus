<!--
	What breaks and what only degrades if one adapter goes: `GET /dependencies/remove/{adapter}`
	(ADR-0147 §3).
-->
<script lang="ts">
	import { page } from '$app/state';
	import { removePath, type RemoveView } from '../../../../lib/acting';
	import DependenciesView from '../../../../lib/DependenciesView.svelte';
	import Reading from '../../../../lib/Reading.svelte';

	const path = $derived(removePath(page.params.adapter ?? ''));
</script>

<Reading {path} reading="Reading what depends on it…">
	{#snippet children(remove: RemoveView)}
		<DependenciesView {remove} />
	{/snippet}
</Reading>
