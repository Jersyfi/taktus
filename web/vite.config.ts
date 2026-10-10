// The web app is a static build the `api` role serves under `{prefix}/app/` (ADR-0063).
// The prefix is the instance's, set when it starts, not when the app is built: the router
// therefore reads the route from the hash, and every path in the build is relative.
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [
		sveltekit({
			adapter: adapter({ pages: 'build', assets: 'build', strict: true }),
			router: { type: 'hash' },
			paths: { relative: true }
		})
	],
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node'
	}
});
