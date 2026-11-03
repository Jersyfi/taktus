<!--
	The stages of one run, for a participant (UC-6.15). The page is `StagesPage`.
-->
<script lang="ts">
	import { page } from '$app/state';
	import StagesPage from '../../../lib/StagesPage.svelte';
</script>

<StagesPage runId={page.params.id ?? ''} />
