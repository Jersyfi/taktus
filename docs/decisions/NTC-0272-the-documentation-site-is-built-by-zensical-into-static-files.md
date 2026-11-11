# NTC-0272 — The documentation site is built by Zensical into static files

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-12
**Raised in:** the branch `concept/release-1-0`, for DEC-0234
**How it follows:** DEC-0234 leaves the tool to the session and fixes the host: web hosting that
serves files. Principle 9 (efficiency over verbosity) and principle 13 (freedom instead of
lock-in) favour plain files built by an open-source tool, and CLAUDE.md §7 favours the
repository's one server-side language. Of the tools that build plain files, only a
Python-based one keeps §7; of those, the maintained successor is taken over the final release.

## 1. What was decided

The guides are rendered from the repository as before (`taktusctl guides publish --to DIR`).
Zensical builds those Markdown files into a static site of HTML files. The site is copied to the
web hosting as plain files, and its search runs in the reader's browser. The configuration lives
in the repository, and `make docs-site` builds the site.

## 2. The evidence

- **Web hosting serves files.** The owner's hosting at IONOS serves static files and runs no
  build. A static site needs nothing on the server.
- **One server-side language.** Zensical is written for Python, like the rest of the repository
  (CLAUDE.md §7). It needs no second toolchain.
- **The successor, not the end of a line.** Material for MkDocs announced its last version,
  9.7.0, on 2025-11-11, with critical fixes "for 12 month at least". MkDocs 1.x is called
  unmaintained on the same blog. Zensical is the successor by the same team, MIT-licensed, and it
  reads an existing `mkdocs.yml`. On PyPI it stands at 0.1.1, *Development Status: Beta*, last
  released 2026-11-10.
- **Beta risk is contained.** The output is plain files; a build that fails publishes nothing.
  The configuration is MkDocs-shaped, so the last Material release builds the same sources.

## 3. What was considered

- **Material for MkDocs 9.7.0.** Rejected: it is final, and its fixes end around now.
- **Astro Starlight.** Mature, static and with search in the browser. Rejected: it adds a
  Node build for the documentation, beside the web app's, for no gain the readers would see.
- **BookStack (NEED-0021).** Rejected for this: it needs a server with a database. The hosting
  serves files, and the wiki was never provided.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.27, a mode-1 entry: the tool that builds documentation from the repository's Markdown is the
session's choice, as long as the result is plain files.
