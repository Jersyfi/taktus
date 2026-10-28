<!--
	Everything that acts for the tenant: `GET /register` (ADR-0147 §2), read on opening and again
	after a stop. The stop is ADR-0138's, sent as the signed-in reader; the inventory is fetched and
	handed to the reader as a file, marked as not legally reviewed.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import { INVENTORY, REGISTER, stopAdapter, type Register } from '../../lib/acting';
	import Reading from '../../lib/Reading.svelte';
	import RegisterView from '../../lib/RegisterView.svelte';

	let round = $state(0);
	const path = $derived(`${REGISTER}?r=${round}`);

	async function onStop(adapter: string): Promise<string | null> {
		const answer = await stopAdapter(surface(location.href), adapter);
		if (!answer.ok) return answer.problem.detail || answer.problem.title;
		round += 1;
		return null;
	}

	async function onInventory() {
		const answer = await read<unknown>(surface(location.href), INVENTORY);
		if (!answer.ok) return;
		const file = new Blob([JSON.stringify(answer.body, null, 2)], { type: 'application/json' });
		const link = document.createElement('a');
		link.href = URL.createObjectURL(file);
		link.download = 'ai-inventory-not-legally-reviewed.json';
		link.click();
		URL.revokeObjectURL(link.href);
	}
</script>

<Reading {path} reading="Reading what acts…">
	{#snippet children(register: Register)}
		<RegisterView {register} {onStop} {onInventory} />
	{/snippet}
</Reading>
