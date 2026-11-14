<!--
	The value ledger (UC-9.1 to UC-9.3, UC-6.7, ADR-0244): `GET /value/proposals`,
	`GET /value/index` and `GET /value/transformation`, read once on opening, each on its own: a
	part the surface refuses says so and leaves the others standing.
-->
<script lang="ts">
	import Skeleton from '../../lib/Skeleton.svelte';
	import { read, surface, type Answer } from '../../lib/api';
	import type { Proposals, Transformation, ValueIndex } from '../../lib/figures';
	import SignInForm from '../../lib/SignInForm.svelte';
	import ValueView from '../../lib/ValueView.svelte';

	let signedIn = $state(true);
	let read_ = $state(false);
	let proposals: Proposals | null = $state(null);
	let index: ValueIndex | null = $state(null);
	let transformation: Transformation | null = $state(null);
	let problems = $state<{ proposals?: string; index?: string; transformation?: string }>({});

	function said<T>(answer: Answer<T>): string | undefined {
		if (answer.ok) return undefined;
		if (answer.problem.status === 401) signedIn = false;
		return answer.problem.detail || answer.problem.title;
	}

	$effect(() => {
		if (!signedIn) return;
		const base = surface(location.href);
		void Promise.all([
			read<Proposals>(base, 'value/proposals'),
			read<ValueIndex>(base, 'value/index'),
			read<Transformation>(base, 'value/transformation')
		]).then(([p, i, t]) => {
			proposals = p.ok ? p.body : null;
			index = i.ok ? i.body : null;
			transformation = t.ok ? t.body : null;
			problems = { proposals: said(p), index: said(i), transformation: said(t) };
			read_ = true;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if read_}
	<ValueView {proposals} {index} {transformation} {problems} />
{:else}
	<Skeleton label="Reading the value ledger…" />
{/if}

