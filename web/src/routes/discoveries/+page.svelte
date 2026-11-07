<!--
	Processes nobody wrote down (UC-9.4, ADR-0245 §2): `GET /discoveries` and the interview's
	questions, `GET /discoveries/interview?mode=`, on opening; `POST /discoveries` makes one
	visible, `POST /discoveries/interview` writes one down from the answers,
	`POST /discoveries/{id}/stages/{stage}` takes a record to its next stage and
	`POST /discoveries/{id}/agree` shares a pattern found for the reader. After each act the page
	reads the records again.
-->
<script lang="ts">
	import { read, send, surface, type Answer } from '../../lib/api';
	import DiscoveriesView from '../../lib/DiscoveriesView.svelte';
	import type { Discoveries, Interview, Interviewed, Mode, Origin, Stage } from '../../lib/discoveries';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';

	let signedIn = $state(true);
	let discoveries: Discoveries | null = $state(null);
	let interview: Interview | null = $state(null);
	let interviewed: Interviewed | null = $state(null);
	let problem: string | null = $state(null);
	let busy = $state(false);

	const base = () => surface(location.href);

	function refused<T>(answer: Answer<T>): boolean {
		if (answer.ok) return false;
		if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
		return true;
	}

	async function load() {
		const answer = await read<Discoveries>(base(), 'discoveries');
		if (!refused(answer) && answer.ok) discoveries = answer.body;
	}

	async function mode(chosen: Mode) {
		const answer = await read<Interview>(base(), `discoveries/interview?mode=${chosen}`);
		if (!refused(answer) && answer.ok) interview = answer.body;
	}

	$effect(() => {
		if (!signedIn) return;
		void load();
		void mode('guided');
	});

	async function act<T>(sent: Promise<Answer<T>>): Promise<Answer<T>> {
		busy = true;
		problem = null;
		const answer = await sent;
		busy = false;
		if (!refused(answer)) await load();
		return answer;
	}

	function discover(body: { title: string; origin: Origin; found: string }) {
		void act(send<unknown>(base(), 'discoveries', body));
	}

	async function write(answers: Record<string, string>) {
		busy = true;
		problem = null;
		const answer = await send<Interviewed>(base(), 'discoveries/interview', { answers });
		busy = false;
		if (!refused(answer) && answer.ok) interviewed = answer.body;
	}

	function advance(id: string, stage: Exclude<Stage, 'visible'>, body: Record<string, unknown>) {
		void act(send<unknown>(base(), `discoveries/${encodeURIComponent(id)}/stages/${stage}`, body));
	}

	function agree(id: string) {
		void act(send<unknown>(base(), `discoveries/${encodeURIComponent(id)}/agree`, {}));
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if discoveries}
	<DiscoveriesView
		{discoveries}
		{interview}
		{interviewed}
		{problem}
		{busy}
		onDiscover={discover}
		onMode={mode}
		onInterview={write}
		onAdvance={advance}
		onAgree={agree}
	/>
{:else if problem}
	<Unavailable eyebrow="Discoveries" {problem} />
{:else}
	<p class="status">Reading the discovered processes…</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
