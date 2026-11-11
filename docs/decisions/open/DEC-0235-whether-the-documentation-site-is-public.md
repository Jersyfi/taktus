# DEC-0235 — Whether the documentation site is public

**Category:** NON-BLOCKING
**Raised in:** the branch `concept/release-1-0`, for DEC-0234
**Issue:** [#679](https://github.com/Jersyfi/taktus/issues/679)
**Needed by:** 2026-11-19
**Provisional answer:** the site asks for a sign-in: the hosting's directory is protected by a password, and only people you give it to can read it.

## 1. What this is about

The documentation of release 1.0 will be a website on your web hosting (DEC-0234). A website is
either readable by anyone, or only after signing in.

## 2. Why you are being asked

Entry M3.7 of `docs/decisions/anchors.taktus.md`: anything published under the project's name is
yours. NEED-0021 had said the guides are never public until someone decides it.

**Sources checked:** `docs/vision/` (principle 11, European sovereignty, and principle 13,
freedom instead of lock-in, set no rule for publishing documentation); DEC-0234 (hosting chosen,
public not stated); NEED-0021 §5 (never public without a decision); DEC-0044 (the licence, open:
the code is "all rights reserved"); ADR-0065 (the guides rendered from the repository, which
names no place); both anchor pages (M3.7 makes publishing the owner's; no mode-1 or mode-2
entry covers it); the register (no decision on publishing documentation). None of them says
whether the documentation is public.

## 3. What you must decide

Is the documentation site readable by anyone, or only after signing in?

## 4. What you need to know to decide

- The repository is already public. Its Markdown says everything the site says. A public site
  makes it easier to read, not more secret or less.
- The site names the project and its features. A public site is a statement under the project's
  name, read by customers, competitors and search engines.
- The licence is still open (DEC-0044). A public developer guide invites building on Taktus
  while nobody may yet use it without your permission.
- A protected site is a password on the hosting's directory (`.htaccess`). You hand it to the
  customer and to anyone you choose. It can be removed at any time.

## 5. Options

### Option A — Protected until the licence is decided (recommended)

- **Meaning:** the site asks for a password. When DEC-0044 is answered, this question comes back.
- **Consequence:** the customer reads it from the first day; nothing is published under the
  project's name before the licence says what may be done with Taktus.
- **Effort:** none beyond the password.
- **Reversibility:** a file removed from the hosting.
- **Why recommended:** a public invitation to build on Taktus fits once the licence allows it.

### Option B — Public now

- **Meaning:** anyone can read it, and search engines find it.
- **Consequence:** the documentation works as the project's front page.
- **Effort:** none.
- **Reversibility:** taking it down is easy; what was indexed and copied stays.

## 6. What is blocked

Nothing. The site is built either way; the upload waits for NEED-0043.

## 7. How to answer

- "DEC-0235: Option A."
- "DEC-0235: Option B."
