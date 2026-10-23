<!--
	A run opened at the trace inside one of its steps: the link a share hands on (UC-6.14,
	ADR-0135). It opens only for a signed-in identity that may see the trace; anyone else signs in,
	or is told the trace is not shown to them.
-->
<script lang="ts">
	import { page } from '$app/state';
	import RunPage from '../../../../../lib/RunPage.svelte';
</script>

<RunPage runId={page.params.id ?? ''} named={page.params.step} />
