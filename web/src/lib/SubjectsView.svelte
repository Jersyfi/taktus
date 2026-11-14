<!--
	Data-protection requests (ADR-0176, UC-11.2). A request is prepared from a kind and the
	subject's identifier; what Taktus holds is shown before anything happens. Carrying it out is
	the person's act: the page says back what will happen, asks for the statement that the
	requester's identity was checked, and only then sends the confirmation. An export is offered
	as a file to save; Taktus keeps no copy. The processing evidence is linked, generated and not
	legally reviewed.
-->
<script lang="ts">
	import { KINDS, exportFile, notConfirmable, sayBack, type RequestKind, type RequestLine, type SubjectRequest } from './subjects';

	let {
		requests,
		open = null,
		message = null,
		busy = false,
		onPrepare,
		onOpen,
		onConfirm,
		onWithdraw
	}: {
		requests: RequestLine[];
		open?: SubjectRequest | null;
		message?: string | null;
		busy?: boolean;
		onPrepare: (kind: RequestKind, subject: string) => void;
		onOpen: (id: string) => void;
		onConfirm: (id: string) => void;
		onWithdraw: (id: string) => void;
	} = $props();

	let kind: RequestKind = $state('access');
	let subject = $state('');
	let checked = $state(false);
	const refused = $derived(open ? notConfirmable(open) : null);
	const file = $derived(open ? exportFile(open) : null);
	const href = $derived(file ? URL.createObjectURL(new Blob([file.text], { type: 'application/json' })) : null);
</script>

<section class="subjects" aria-labelledby="subjects-title">
	<p class="eyebrow">Data protection</p>
	<h1 id="subjects-title">
		{requests.length === 0 ? 'No data-protection request yet.' : `${requests.length} ${requests.length === 1 ? 'request' : 'requests'} of this tenant.`}
	</h1>
	<p class="muted">
		Taktus finds what it holds of a subject through the case scopes of its runs, and a person carries the request out.
		The ledger names the request, never the subject. <a href="#/subjects/evidence">The processing evidence</a> is generated, not legally reviewed.
	</p>
	{#if message}<p class="message" role="status">{message}</p>{/if}

	<form
		class="prepare"
		onsubmit={(e) => {
			e.preventDefault();
			if (subject.trim()) onPrepare(kind, subject.trim());
			subject = '';
		}}
	>
		<label
			>Kind
			<select bind:value={kind}>
				{#each KINDS as k (k)}<option value={k}>{k}</option>{/each}
			</select>
		</label>
		<label>The subject's identifier <input type="text" bind:value={subject} autocomplete="off" /></label>
		<button type="submit" disabled={busy || !subject.trim()}>Prepare</button>
	</form>

	{#if open}
		<article class="request" data-request={open.id} aria-label="Request {open.id}">
			<h2>{open.kind} — {open.state.replace('_', ' ')}</h2>
			<p>
				Holds {open.holds.runs} {open.holds.runs === 1 ? 'run' : 'runs'} and {open.holds.objects}
				{open.holds.objects === 1 ? 'object' : 'objects'}{open.holds.kept ? `, ${open.holds.kept} shared with another run` : ''}.
			</p>
			{#if refused}
				<p class="muted">{refused}</p>
			{:else}
				<p class="reading">{sayBack(open)}</p>
				<label class="check"><input type="checkbox" bind:checked /> I checked that the person asking is the subject, or may act for them.</label>
				<button type="button" class="primary" disabled={busy || !checked} onclick={() => { onConfirm(open.id); checked = false; }}>Carry it out</button>
				<button type="button" disabled={busy} onclick={() => onWithdraw(open.id)}>Withdraw</button>
			{/if}
			{#if file && href}
				<p><a {href} download={file.name}>Save the export</a> — Taktus keeps no copy.</p>
			{/if}
		</article>
	{/if}

	<ul class="list">
		{#each requests as r (r.id)}
			<li data-line={r.id}>
				<span class="id">{r.id}</span>
				<strong>{r.kind}</strong>
				<span>{r.state.replace('_', ' ')}</span>
				<span class="muted">prepared {r.created_at.slice(0, 10)} by {r.prepared_by}</span>
				<button type="button" class="quiet" disabled={busy} onclick={() => onOpen(r.id)}>Open</button>
			</li>
		{/each}
	</ul>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.id {
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		color: var(--text-subtle);
	}
	.list {
		list-style: none;
		padding: 0;
		max-width: 46rem;
	}
	.list li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: baseline;
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--border-subtle);
	}
	form {
		display: flex;
		gap: 0.5rem;
		align-items: end;
		flex-wrap: wrap;
		max-width: 46rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: var(--fs-100);
	}
	label.check {
		flex-direction: row;
		align-items: center;
		margin: 0.5rem 0;
	}
	input[type='text'],
	select {
		font: inherit;
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-md);
		background: var(--bg-canvas);
		color: var(--text-primary);
	}
	.request {
		margin-top: 1.25rem;
		max-width: 46rem;
		padding: 1rem;
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-lg);
	}
</style>
