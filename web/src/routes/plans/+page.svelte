<!--
	The plan dialogue (UC-1.2) and the guided start (UC-10.3): `#/plans`: the reader's
	plans, and one draft at a time. Reads `GET /plans`, `GET /plans/templates` and `GET /plans/{draft}?mode=`;
	answers with `POST /plans/{draft}/answers`, sets with `PATCH /plans/{draft}`, commissions with
	`POST /plans/{draft}/commission` (ADR-0279). The mode is the reader's choice for the visit,
	kept nowhere: it is a preference, never a permission (ADR-0238 §4).
-->
<script lang="ts">
	import { read, send, surface, write, type Answer } from '../../lib/api';
	import PlanView from '../../lib/PlanView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { Problem } from '../../lib/types';
	import type { Mode, PlanDraftView, Template } from '../../lib/workspace';

	let signedIn = $state(true);
	let plans: PlanDraftView[] = $state([]);
	let templates: Template[] = $state([]);
	let view: PlanDraftView | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	let mode: Mode = $state('guided');
	const base = () => surface(location.href);


	let current: string | null = $state(null);

	function refused(problem: Problem) {
		if (problem.status === 401) signedIn = false;
		else message = problem.detail || problem.title;
	}

	async function load() {
		const listed = await read<{ plans: PlanDraftView[] }>(base(), 'plans');
		if (!listed.ok) return refused(listed.problem);
		plans = listed.body.plans;
		const offered = await read<{ templates: Template[] }>(base(), 'plans/templates');
		if (offered.ok) templates = offered.body.templates;
		const id = current;
		if (id) {
			const one = await read<PlanDraftView>(base(), `plans/${encodeURIComponent(id)}?mode=${mode}`);
			if (one.ok) view = one.body;
			else refused(one.problem);
		} else view = null;
	}

	$effect(() => {
		if (!signedIn) return;
		void load();
	});

	async function act(answer: Promise<Answer<PlanDraftView>>) {
		busy = true;
		message = null;
		const done = await answer;
		busy = false;
		if (done.ok) {
			view = done.body;
			current = done.body.draft.id;
		} else refused(done.problem);
	}

	function path(): string {
		return `plans/${encodeURIComponent(view?.draft.id ?? '')}`;
	}

	async function setMode(next: Mode) {
		mode = next;
		if (view) await act(read<PlanDraftView>(base(), `${path()}?mode=${next}`));
	}

	async function commission(accepted = false) {
		busy = true;
		const where = `${path()}/commission${accepted ? '?accept_demand=true' : ''}`;
		const done = await send<{ id: string; status: string }>(base(), where, {});
		busy = false;
		if (!done.ok && done.problem.demand && !accepted) {
			// The run it starts needs much: its estimated demand is shown first (ADR-0299).
			if (confirm(`${done.problem.detail}\n\nAccept this demand and commission?`))
				return commission(true);
		}
		if (done.ok) {
			message = `Commissioned as ${done.body.id}. It runs as planned from now on.`;
			await load();
		} else refused(done.problem);
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else}
	<PlanView
		{view}
		{plans}
		{templates}
		{busy}
		{message}
		onOpen={(said) => void act(send<PlanDraftView>(base(), 'plans', { said }))}
		onPick={(id) => {
			current = id;
			void load();
		}}
		onAnswer={(field, value, stepId) =>
			void act(send<PlanDraftView>(base(), `${path()}/answers`, { field, value, step_id: stepId }))}
		onSet={(fields) => void act(write<PlanDraftView>(base(), path(), 'PATCH', { fields }))}
		onMode={(m) => void setMode(m)}
		onCommission={() => void commission()}
	/>
{/if}
