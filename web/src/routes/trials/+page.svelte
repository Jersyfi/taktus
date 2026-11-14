<!--
	The model trials and those offered (#448, ADR-0149): `GET /trials`; a trial is started with
	`POST /trials`, with any cases the person names, and the page then opens it. An offer is declined
	with `POST /trials/offers/decline`, and the page reads the trials again.
-->
<script lang="ts">
	import Skeleton from '../../lib/Skeleton.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';
	import { read, send, surface } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import TrialsView from '../../lib/TrialsView.svelte';
	import { trialsLink, type NamedCase, type Offer, type Trial, type Trials } from '../../lib/spend';

	let signedIn = $state(true);
	let trials: Trials | null = $state(null);
	let problem: string | null = $state(null);

	async function load() {
		const answer = await read<Trials>(surface(location.href), 'trials');
		if (answer.ok) trials = answer.body;
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}

	$effect(() => {
		if (signedIn) void load();
	});

	async function decline(offer: Offer, reason: string) {
		problem = null;
		const answer = await send<unknown>(surface(location.href), 'trials/offers/decline', {
			purpose: offer.purpose,
			occasion: offer.occasion,
			model: offer.model,
			reason
		});
		if (answer.ok) await load();
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}

	async function start(purpose: string, candidates: string[], occasion: string, cases: NamedCase[] = []) {
		problem = null;
		const body = cases.length ? { purpose, candidates, occasion, cases } : { purpose, candidates, occasion };
		const answer = await send<Trial>(surface(location.href), 'trials', body);
		if (answer.ok) location.hash = trialsLink(answer.body.id);
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if trials}
	<TrialsView {trials} {problem} onStart={start} onDecline={decline} />
{:else if problem}
	<Unavailable eyebrow="Trials" {problem} />
{:else}
	<Skeleton label="Reading the model trials…" />
{/if}

