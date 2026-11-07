<!--
	The organisation's structure, the reader's projects and their session (UC-1.4, UC-1.6, UC-1.8):
	reads `GET /structure` and `GET /projects`; shapes with `PUT /structure/levels`,
	`POST /structure/units`, `PUT /structure/placements/{kind}/{name}`,
	`PUT /structure/knowledge/{unit}`; asks `GET /structure/filings/{kind}/{name}`; creates with
	`POST /projects`; opens, continues and settles a session with `POST /projects/{p}/session`,
	`POST /sessions/{s}/turns` and `POST /sessions/{s}/plan` (ADR-0279).
-->
<script lang="ts">
	import { read, send, surface, write, type Answer } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import StructureView from '../../lib/StructureView.svelte';
	import type { Session, Structure, Unit } from '../../lib/workspace';

	let signedIn = $state(true);
	let structure: Structure | null = $state(null);
	let projects: Unit[] = $state([]);
	let session: Session | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);
	const part = encodeURIComponent;

	async function load() {
		const shown = await read<Structure>(base(), 'structure');
		if (!shown.ok) {
			if (shown.problem.status === 401) signedIn = false;
			else message = shown.problem.detail || shown.problem.title;
			return;
		}
		structure = shown.body;
		const listed = await read<{ projects: Unit[] }>(base(), 'projects');
		if (listed.ok) projects = listed.body.projects;
	}

	$effect(() => {
		if (!signedIn) return;
		void load();
	});

	async function act<T>(answer: Promise<Answer<T>>, said: (body: T) => string): Promise<T | null> {
		busy = true;
		const done = await answer;
		busy = false;
		if (!done.ok) {
			message = done.problem.detail || done.problem.title;
			return null;
		}
		message = said(done.body);
		await load();
		return done.body;
	}

	async function openSession(project: string) {
		const opened = await act(send<Session>(base(), `projects/${part(project)}/session`, {}), () => '');
		if (opened) session = opened;
	}

	async function say(text: string) {
		if (!session) return;
		await act(send(base(), `sessions/${part(session.id)}/turns`, { text }), () => '');
		await openSession(session.project);
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if structure}
	<StructureView
		{structure}
		{projects}
		{session}
		{busy}
		{message}
		onAddUnit={(id, name, parent) => void act(send(base(), 'structure/units', { id, name, parent }), () => `${name} added.`)}
		onPlace={(kind, name, unit) =>
			void act(write(base(), `structure/placements/${part(kind)}/${part(name)}`, 'PUT', { unit }), () => `${name} is in ${unit} now.`)}
		onLevels={(levels) => void act(write(base(), 'structure/levels', 'PUT', { levels }), () => 'The levels are named.')}
		onKnowledge={(unit, link) =>
			void act(write(base(), `structure/knowledge/${part(unit)}`, 'PUT', { base: link }), () => `${unit} files its documentation there now.`)}
		onWhere={(kind, name) =>
			void act(read<{ places: { kind: string; link: string }[] }>(base(), `structure/filings/${part(kind)}/${part(name)}`), (f) =>
				`Documented at: ${f.places.map((p) => p.link).join(', ')}`)}
		onCreateProject={(id, name, circle, unit) =>
			void act(send(base(), 'projects', { id, name, circle, ...(unit ? { unit } : {}) }), () => `${name} created.`)}
		onOpenSession={(p) => void openSession(p)}
		onSay={(text) => void say(text)}
		onPlan={(goal) =>
			session && void act(send<{ ref: string }>(base(), `sessions/${part(session.id)}/plan`, { goal }), (o) => `A plan draft ${o.ref} waits in Plans.`)}
	/>
{:else}
	<p class="status">{message ?? 'Reading the structure…'}</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
