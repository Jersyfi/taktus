<!--
	The start page's section of what keeps the operation running, read once as the signed-in
	reader from `GET /operation` (ADR-0121, ADR-0119). Self-contained, so that the start page holds it as one
	line. A read that fails leaves the section out; the overview stands without it.
-->
<script lang="ts">
	import { read, surface } from './api';
	import type { OperationSummary } from './operation';
	import OperationLines from './OperationLines.svelte';

	let summary: OperationSummary | null = $state(null);

	$effect(() => {
		void read<OperationSummary>(surface(location.href), 'operation').then((answer) => {
			summary = answer.ok ? answer.body : null;
		});
	});
</script>

{#if summary}
	<OperationLines {summary} />
{/if}
