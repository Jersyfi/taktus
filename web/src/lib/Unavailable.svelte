<!--
	A page the surface did not serve to this reader: its eyebrow, and the surface's own sentence
	saying why, as the page's heading. Without it the page showed the bare sentence and no name.
-->
<script lang="ts">
	let { eyebrow, problem }: { eyebrow: string; problem: string } = $props();

	const sentence = $derived.by(() => {
		const said = problem.trim();
		const capital = said.charAt(0).toUpperCase() + said.slice(1);
		return /[.!?)]$/.test(capital) ? capital : `${capital}.`;
	});
</script>

<section aria-labelledby="unavailable-title">
	<p class="eyebrow">{eyebrow}</p>
	<h1 id="unavailable-title" role="alert">{sentence}</h1>
</section>

<style>
	h1 {
		max-width: 28ch;
		font-size: clamp(1.4rem, 3vw, 2rem);
	}
</style>
