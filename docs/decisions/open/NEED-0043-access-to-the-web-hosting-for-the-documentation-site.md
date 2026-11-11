# NEED-0043 — Access to the web hosting for the documentation site

**Kind:** access
**Raised in:** the branch `concept/release-1-0`, for DEC-0234
**Issue:** [#680](https://github.com/Jersyfi/taktus/issues/680)
**Needed by:** 2026-11-19
**Foreseeable since:** DEC-0234, where the owner chose the web hosting at IONOS for the documentation

## 1. What is needed

1. **An address** under which the documentation is reached, such as a subdomain of a domain you
   hold, pointed at a directory of the web hosting and served over HTTPS.
2. **An SFTP login** of the web hosting that may write into that directory.

## 2. Why

DEC-0234: the documentation is hosted on the owner's web hosting. The site is a set of plain
files (NTC-0272); the session copies them there over SFTP. Nothing else is needed on the server.

## 3. By when

**2026-11-19**, a week after release 1.0's pull request. Until then the site is built and checked
on every change, and nothing is uploaded.

## 4. How to provide it

**Step 1 — the directory and the address.** In the IONOS customer area, under *Domains & SSL*,
choose the domain or subdomain the documentation is to live under. Set its use to *Webspace* and
name a new directory, for example `/taktus-docs`. Activate its SSL certificate there.

**Step 2 — the login.** Under *Hosting*, open the package, then *SFTP & SSH*. Create an SFTP user
whose access is limited to that directory, if the package allows it; otherwise use the main
SFTP user. The page shows the server's host name.

**Step 3 — into the vault.** In 1Password, in the vault `Development`, create an item named
`IONOS docs SFTP` of the kind *Server*. Give it the fields `host`, `username`, `password` and
`path` (the directory of step 1), and the address of step 1 as its website. The session reads it
from there through its own service account (DEC-0224), into a file and never onto a screen.

**Step 4 — the answer.** Write in the issue: **"NEED-0043 is provided."**

## 5. What it must never be

- **Never in this repository**, a chat or an issue: not the password, and not the host name or
  the address, which are the deployment's own names (CLAUDE.md §9). They stay in the vault and the
  private note.
- **Never your IONOS account's own password.** An SFTP user is a login of the hosting alone.

## 6. What happens next

The session records the need as provided, uploads the site after asking you once (publishing is
an outward act), and confirms the address answers.

## 7. How to confirm

The address of step 1 shows the documentation's start page over HTTPS. Whether a reader must
sign in first is DEC-0235.
