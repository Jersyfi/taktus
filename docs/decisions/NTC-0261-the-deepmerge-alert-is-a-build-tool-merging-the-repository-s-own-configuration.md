# NTC-0261 — The `deepmerge` alert is a build tool merging the repository's own configuration

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-04
**Raised in:** branch `concept/package-e--ci` (package E, concept mode, DEC-0222), for the open
Dependabot alerts of DEC-0227 item 4
**How it follows:** DEC-0227 item 4 has the open security alerts fixed by upgrades. For
`deepmerge` no upgrade exists, and the package that pulls it has no release without it. Principle
12 (production-ready) gives Taktus "the obligations of any critical system": a known weakness
in what it ships is removed, or shown not to reach anything. Writing a merge of our own in place of a maintained library would add code to the
build toolchain to silence a finding that cannot apply. Of the two options consistent with the
sources, the stricter in substance is to show precisely what the function receives, and to
watch for a release that fixes it; the one with less ceremony is not to fork a build tool.

## 1. What was decided

The alert GHSA-gcqx-w48m-w2h4 on `deepmerge` 4.3.1 in `web/package-lock.json` is not fixed by
an upgrade, because none exists. It is dismissed as a tolerable risk once this record is on
`main`, with this record named as the reason. The dependency stays.

## 2. The evidence

- **The advisory:** `deepmerge`'s `mergeObject()` copies a `__proto__` key of its input into
  the object it returns, so that merging data an attacker controls can poison that object's
  prototype. Every version from 4.2.0 to 4.3.1 is affected, and 4.3.1 of 2023-03-16 is the newest
  release; the advisory lists no patched version.
- **Who pulls it:** only `@sveltejs/vite-plugin-svelte` 7.3.1, the newest release, which
  declares `deepmerge: ^4.3.1` (`npm view @sveltejs/vite-plugin-svelte@latest dependencies`).
  It is a development dependency (`"dev": true` in the lock file).
- **What it merges:** one call, in `src/utils/options.js` of the plugin, `mergeConfigs()`. Its
  inputs are the plugin's default options, a `svelte.config.js` where one exists (`web/` has
  none), the options of `web/vite.config.ts` and options the plugin itself adds. Each is code of this repository or of
  the plugin, read when `vite` builds or serves the web app on a developer's machine or in CI.
  No request, no tenant's data and no file from outside reaches it.
- **What ships:** the web app's build output (`web/build`), which the control plane serves, is
  the compiled pages. The plugin and `deepmerge` run only while building it and are not part of
  it.

## 3. What was considered

- **An npm `overrides` entry pointing `deepmerge` at a merge of our own.** Rejected: it adds a
  hand-written copy of a library to the build toolchain, to be maintained beside it, to remove a
  weakness no input can reach.
- **Another library in its place through `overrides`.** Rejected: none offers `deepmerge`'s
  interface (`arrayMerge`, its handling of non-plain objects) by contract, and a silent change of
  how the web app's build options are merged is a real risk where the present one is none.
- **Removing `@sveltejs/vite-plugin-svelte`.** Not possible: it is how SvelteKit compiles the
  web app, the stack of CLAUDE.md §7.

## 4. Which entry permits it

M2.6: no entry of `docs/decisions/anchors.taktus.md` covers a security alert without a fix. The
owner may overrule it in the pull request.

## 5. The entry it proposes

**M2.12** — *A security alert on a dependency for which no fixed version exists is dismissed as
a tolerable risk when a notice shows every input the affected function receives and that none
comes from outside the repository; the alert is reopened, and the dependency upgraded, as soon
as a fixed version or a release of the dependent package without it appears.*
