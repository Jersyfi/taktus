# NEED-0021 — A wiki for the guides

**Kind:** account
**Raised in:** the pull request for issue [#88](https://github.com/Jersyfi/taktus/issues/88)
**Issue:** [#199](https://github.com/Jersyfi/taktus/issues/199)
**Needed by:** 2026-11-14
**Foreseeable since:** the pull request for issue [#88](https://github.com/Jersyfi/taktus/issues/88), where the guides were first rendered and published to a directory of files

## 1. What is needed

Taktus now writes two guides from its own repository: one for the people who install and run it,
one for the people who use it. They are to be read in a wiki, not in the repository. You decided on
2026-10-08 that a wiki is connected for the documentation once Taktus manages itself, and that the
session says what you are to create (DEC-0057). This is it:

1. **A wiki of the product BookStack**, run by you, reachable over HTTPS from Taktus's instance, and
   readable only after signing in. It is not public.
2. **One shelf and two books in it**, where the guides go: the shelf `Taktus`, with the books
   `Administration` and `Using Taktus`.
3. **An account for Taktus in it**, with a role that may use the wiki's interface for programs and
   create, change and read pages in those two books, and nothing else.
4. **A token of that account** for the interface, put where the instance reads its secrets.
5. **The wiki's address**, in the private note where the platform's names are kept.

Why BookStack. It is open source under the MIT licence, so no decision against a vendor ends the
guides (principle 13). It runs on your own machines in the EU (principle 11). It structures pages
as shelves, books and pages, which is the place a guide names: shelf, book, page. Its interface for
programs reads and writes a page's text as Markdown and keeps tags beside a page, where Taktus can
keep its mark. It can export every book as files. Wiki.js would also do; BookStack is proposed for
its interface for programs, which is plain HTTP with a token, where Wiki.js asks for queries in a
language of its own.

## 2. Why

UC-13.6 asks that the guides be placed in the organisation's own knowledge system. Until this
exists the guides go to a directory of files (`taktusctl guides publish --to`), which is the use
case's answer for an organisation without a wiki, and nobody reads them there. The connector to
the wiki is issue #197; its live test needs this wiki and this token. The daily process that keeps
the guides current is issue #198; it can run against the directory without the wiki.

## 3. By when

**2026-11-14**, so that #197 can be proven against the real wiki within the milestone `0.3.0`.

If it is not there by then: #197 is built and proven against a fake of the wiki's interface only,
and the guides stay in files. Nothing else waits.

## 4. How to provide it

**Step 1 — the wiki.** Run BookStack where you run Taktus's other services. Recommended: on the
production cluster, in a namespace of its own and never in one of Taktus's two namespaces, with
the official container image of the current release, its own database on a volume, and the volume
in the same backup as Taktus's database (NEED-0009). Reach it over HTTPS under a name of yours.
Under *Settings → Features & Security*, leave *Public access* off. Taktus does not install it:
an instance does not administer the platform it runs on (ADR-0025).

**Step 2 — the place.** Signed in as an administrator, create the shelf `Taktus` and, on it, the
books `Administration` and `Using Taktus`. Taktus creates the pages in them.

**Step 3 — the account.** Under *Settings → Roles*, create the role `Taktus guides` with:

- *System permissions*: only *Access system API*;
- *Asset permissions*: none at all;
- on each of the two books, under the book's *Permissions*: for `Taktus guides`, *View*, *Create*
  and *Update*; never *Delete*.

Under *Settings → Users*, create the user `Taktus` with that role and no other, and an address you
read. Nobody signs in as it.

**Step 4 — the token.** Open the user `Taktus`, then *API Tokens → Create Token*. Name it
`taktus-guides`, and let it expire after one year. The wiki shows a *Token ID* and a *Token
Secret* once. Join them as `<id>:<secret>` and write that into a file only you can read, then into
the instance's secret store under the parameter `KNOWLEDGE_TOKEN`: on the cluster, a Secret in the
control plane's namespace, named in the chart's `credentials` (`deploy/k8s/README.md` §2). The
parameter is described in `CREDENTIALS.md` when #197 brings the code that reads it.

```sh
kubectl --namespace "<control-plane namespace>" create secret generic "<secret name>" \
  --from-file=token="<path of the file with id:secret>"
```

Renew it before it expires: create a new token, replace the Secret, delete the old token in the
wiki.

**Step 5 — the address.** Write the wiki's base address into the private note, under "wiki for the
guides".

## 5. What it must never be

- **Never public.** The guides are derived from a public repository, but a public wiki would be a
  statement under the project's name (M3.7), and nobody decided that.
- **Never an administrator's token**, and never your own: the token belongs to the user `Taktus`,
  whose role can neither delete a page nor reach another book.
- **Never in this repository**, a chat, an issue or an environment variable a process listing
  shows. The token goes into the file and the Secret, nowhere else.
- **The wiki's address and the Secret's name never in this repository**: they are the
  deployment's own names, and stay in the private note.

## 6. What happens next

Write in the issue: **"NEED-0021 is provided."** The next session records it first. Issue #197
then runs its live test against the wiki, and the guides appear in the two books.

## 7. How to confirm

Without revealing the token, from a machine that reaches the wiki, with the token in a file:

```sh
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  --header "Authorization: Token $(cat "<path of the file with id:secret>")" \
  "<wiki address>/api/books"
```

It prints `200`. Opening `<wiki address>/books` in a private browser window shows the sign-in
page, not the books.
