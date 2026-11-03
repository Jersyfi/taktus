# ADR-0177 — The web app draws with the owner's one design system, in tokens

**Status:** accepted · extends ADR-0059 (one visual vocabulary), ADR-0063 (the web app) and
M1.20 (the look is the session's within UC-6.10's distinctions, DEC-0185) · DEC-0227 item 3;
UC-13.7

## Context

The owner asked for the web app to be redesigned, and for its colours to follow the design
system of his other product, Hubtask (DEC-0227). The aim he named is that one design system
serves all of his applications.

Hubtask's design system is public, under Apache-2.0, and the owner's own. Its foundations are one
file in the W3C design-token format (DTCG): `packages/design-system/tokens/tokens.json`. A *token*
is a named design value. The file holds *primitives* — the colour ramps, spacing, radius, type,
duration, easing, layering and breakpoints — and a *semantic* layer for a light and a dark mode.
The semantic layer names what a value is for: the page, a card, the primary text, a status, the
AI tint. Application code binds only to the semantic layer. A CSS custom property is generated
per token.

Until now the web app chose its own colours in `+layout.svelte`: paper and ink in OKLCH, and one
hue per family of methods. One chart wrote eight hex values of its own. Nothing measured their
contrast.

Two facts bound the answer. The glyphs are the reporting component's (ADR-0059): which form, mark
and motion an element takes is not the web app's to choose. And UC-6.10 requires every
distinction to be carried by form and motion, never by colour alone. Colour is therefore what the
web app may change, and only on top of the form.

## Decision

### 1. Hubtask's foundations, copied unchanged

`web/design/tokens.json` is Hubtask's `tokens.json`, copied unchanged from a named commit. One
key is added at the top, `$source`: the repository, the path, the commit and the licence. Nothing
else in it is edited here. Taking a newer version is a copy of the newer file and a new commit in
`$source`. The values are the owner's, decided in Hubtask; Taktus holds no second opinion of
them.

### 2. Taktus's own layer, beside it

`web/design/taktus.tokens.json` holds what only Taktus needs, in the same format, for both modes.
Every value in it is a reference to a Hubtask primitive, never a literal. It names:

- **The families of methods** (ADR-0059): `reproducible` takes Hubtask's `sky`; `variable` takes
  its `violet`, the hue Hubtask reserves for what an AI proposes; `person` takes its `mint`;
  `waiting` takes its neutrals. An alarm takes Hubtask's `danger`. Each family has a hue for a
  mark and a subtle surface.
- **The series of a chart**: two series, and the four price kinds of a model's tokens (ADR-0148).

Hubtask's `raspberry` stays what Hubtask says it is: the signature, with no system meaning. Taktus
uses it in its mark and in the ambient tint of the page, nowhere else.

### 3. One generated stylesheet

`web/scripts/tokens.js` resolves both files and writes `src/lib/generated/tokens.css`. It runs
before every `npm` script that reads the app — `dev`, `check`, `test` and `build`. The file is
therefore never stored and never edited by hand. The names follow Hubtask's table
(`build/naming.js`): `--sky-600`, `--sp-200`, `--fs-100`, `--bg-canvas`, `--text-primary`,
`--shadow-raised`, `--motion-entrance-duration`. Taktus's layer adds `--family-*` and
`--chart-*`.

The primitives are declared on `:root`. The semantic layer is declared under
`:root[data-theme='light']` and `:root[data-theme='dark']`. A page without the attribute follows
the system's `prefers-color-scheme`. Hubtask leaves that case unstyled, so that a page which
forgets the attribute looks broken at once. The web app is served as static files and paints
before its script runs, so its first paint must already be right. The reader chooses *System*,
*Light* or *Dark*. The choice belongs to the device and is kept in its storage, as Hubtask keeps
it.

### 4. Application code binds to the semantic layer

Every component binds to a semantic token or to Taktus's layer. A colour written as a literal —
hex, `rgb()`, `hsl()`, `oklch()` — in a component's style is refused. So is a reference to a
custom property that no token and no rule in the same file declares. `src/lib/design.test.ts`
holds both.

### 5. Contrast is measured, not asserted

`src/lib/design.test.ts` resolves every token in both modes and measures the WCAG 2.2 contrast:

- primary, secondary and subtle text, the brand text and every status text against the canvas,
  the surface, the raised plane and the sunken plane: at least 4.5:1 (SC 1.4.3);
- every family's hue, every chart series and the focus ring against the surface and the canvas:
  at least 3:1 (SC 1.4.11), since a mark is a graphic.

A token that fails is a failing test, not a remark.

### 6. Type and motion

The type scale, weights and line heights are Hubtask's: IBM Plex Sans for the interface, IBM Plex
Sans Condensed for display, IBM Plex Mono for data. Every movement of the frame takes a
`--motion-<role>` pair. Under reduced motion — the system's, or the reader's *Stop motion* — no
transition of the frame runs. The glyphs keep their still marks as before (ADR-0059 §2).

## Consequences

- The web app and Hubtask draw from the same values. A change of the owner's palette reaches the
  web app by copying one file.
- Every colour the web app shows is measured for contrast in both modes on every test run.
- The look of every page changes; what each page says and draws does not.
- `web/README.md` names the design files.

## Where this promise ends

- **The faces are named, not shipped.** The web app names IBM Plex first in each stack and falls
  back to the system's own sans-serif and monospace faces. It does not ship the font files: they
  would be a new package in the lock file, and a page an instance serves contacts no foreign host
  for a font. Where IBM Plex is not installed, the page is set in the system's face.
- **Hubtask's components are not taken.** Only its foundations are. Its Svelte components belong
  to a different shell and router, and Taktus draws its own levels (ADR-0063).
- **A copy, not a link.** A change in Hubtask reaches Taktus only when its file is copied again.
  No test compares the copy with Hubtask's current file, because a test here reaches no other
  repository.
- **Contrast is measured on opaque planes.** A translucent colour — the glass of the bar, a hue
  mixed into a surface — is measured only where the test names that pair.
- **The glyphs' tokens are unchanged.** Which membrane, nucleus, ring and motion an element takes
  stays the reporting component's (ADR-0059). This decision changes only the hue added on top.
- **Light and dark only.** No high-contrast mode is declared beyond what the system's forced
  colours do to the page.
