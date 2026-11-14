# NTC-0289 — The web design gate refuses a type size or a radius written outside the tokens

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** branch `area/design` (package F, concept mode, DEC-0239)
**How it follows:** CLAUDE.md §11 point 11 makes a hole in a gate's coverage met on the way a
finding, recorded where the gate changes. UC-13.7 §2 requires that "every colour, type size,
spacing and movement of the frame is a token of the design system". The gate checked colours
only.

## 1. What was decided

- `web/src/lib/design.test.ts` and `tests/components/reporting/test_web_design_system.py` now
  refuse a `font-size` and a `border-radius` (any of its long forms) written with a literal length
  in `px`, `rem`, `em`, `pt` or `%` in any style of the web app. A viewport-relative part of a
  `clamp()` stays allowed: it is a rule for scaling, not a size.
- The 140 literal type sizes in 64 files and the 78 literal radii found were bound to the nearest
  token of the design system (`--fs-*`, `--r-*`); `50%` on a round mark became `--r-full`.
- The design system's tokens were copied again from Hubtask at commit `617bd76c5`, as ADR-0177 §1
  prescribes: new sizes `fs-065`, `fs-090`, `fs-450`, the motions `settle`, `highlight`, `reveal`
  and `reorder`, the layout measures of the navigation, the sheet and the dialogs, and
  `accent.star`. The side navigation is 264 px wide instead of 240 px.

## 2. The evidence

- `make gate-web` passes with the new test `write no type size and no radius of their own`.
- `uv run pytest tests/components/reporting/test_web_design_system.py` passes with
  `test_no_page_writes_a_type_size_or_radius_of_its_own`.

## 3. What was considered

- **A notice without the fix.** Rejected: a gate that knows the hole and keeps it open is weaker
  than the use case it serves.
- **Spacing in the same test.** Not built: the web app still writes margins and gaps in `rem` in
  many places, and binding them is a change of layout across every page that this area could not
  check page by page. Spacing stays a known gap of UC-13.7 §2, said in its section 5.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond M2.6: a gate widened to what its use case already requires is a finding fixed on the
way (CLAUDE.md §11).
