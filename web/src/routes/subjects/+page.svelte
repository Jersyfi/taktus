<!--
	Data-protection requests (ADR-0176, UC-11.2): `GET` and `POST /subjects/requests`, one request
	with `GET /subjects/requests/{id}`, and its confirmation and withdrawal. The page reads the list
	again after every act.
-->
<script lang="ts">
	import Skeleton from '../../lib/Skeleton.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';
	import { read, send, surface } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import SubjectsView from '../../lib/SubjectsView.svelte';
	import { subjectsPath, type RequestKind, type RequestLine, type SubjectRequest } from '../../lib/subjects';

	let signedIn = $state(true);
	let requests: RequestLine[] | null = $state(null);
	let open: SubjectRequest | null = $state(null);
	let problem: string | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);

	async function load() {
		const answer = await read<{ requests: RequestLine[] }>(surface(location.href), subjectsPath);
		if (answer.ok) requests = answer.body.requests;
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}

	$effect(() => {
		if (signedIn) void load();
	});

	async function act(path: string, body: unknown) {
		busy = true;
		message = null;
		const answer = await send<SubjectRequest>(surface(location.href), path, body);
		busy = false;
		if (answer.ok) open = answer.body;
		else if (answer.problem.status === 401) signedIn = false;
		else message = answer.problem.detail || answer.problem.title;
		await load();
	}

	async function show(id: string) {
		const answer = await read<SubjectRequest>(surface(location.href), `${subjectsPath}/${encodeURIComponent(id)}`);
		if (answer.ok) open = answer.body;
		else message = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if requests}
	<SubjectsView
		{requests}
		{open}
		{message}
		{busy}
		onPrepare={(kind: RequestKind, subject: string) => act(subjectsPath, { kind, subject })}
		onOpen={show}
		onConfirm={(id: string) => act(`${subjectsPath}/${encodeURIComponent(id)}/confirm`, { identity_checked: true })}
		onWithdraw={(id: string) => act(`${subjectsPath}/${encodeURIComponent(id)}/withdraw`, {})}
	/>
{:else if problem}
	<Unavailable eyebrow="Data protection" {problem} />
{:else}
	<Skeleton label="Reading the data-protection requests…" />
{/if}

