<!--
	The run level of one run, live (UC-6.10, ADR-0063), with what can be done on it: a take-over
	(ADR-0128) and the trace inside each worker step (ADR-0135). The page is `RunPage`.
-->
<script lang="ts">
	import { page } from '$app/state';
	import RunPage from '../../../lib/RunPage.svelte';
</script>

<RunPage runId={page.params.id ?? ''} />
