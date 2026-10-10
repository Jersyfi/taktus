# NTC-0142 — The guides are published without overwriting hand edits

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#88](https://github.com/Jersyfi/taktus/issues/88), in the pull request that closes it

## 1. What was decided

Taktus renders two guides from its repository and puts them into a knowledge system, as issue #88
requires (UC-13.6, ADR-0065). Before, it had no guides and no way to reach a knowledge system. What
the software does now:

- `docs/guides/guides.yaml` declares an administration guide — installing, configuring, operating,
  restoring — and a guide for the people who use Taktus. A page is made of files and sections of
  the repository, and of the words under `docs/guides/` that no other document says.
- `taktusctl guides check` renders every page from a commit and writes nothing. A page whose file
  or section is missing, or that would carry an IPv4 address of an installation or a private key,
  is refused, and nothing is rendered.
- `taktusctl guides publish --to <directory>` puts the guides into a directory, one Markdown file
  per page, through the capability `knowledge.pages` and the new directory connector.
- A page is overwritten only where it holds exactly the text Taktus last wrote there. A page edited
  by hand, or one Taktus did not write, is kept, and its difference from the repository is printed;
  the command then exits `1`. Each guide's contents page lists every page with its state, and shows
  a page edited by hand whose sources changed since as out of date.
- A commit that changes nothing a page says does not rewrite the page. A page the repository no
  longer declares is kept and named on the contents page; nothing is deleted.

Six readings UC-13.6 leaves open were taken the strict way, each following the source that governs
the same question elsewhere:

1. A page at the place that Taktus did not write is treated like a hand edit and kept. UC-13.6
   protects a person's text in the knowledge system; whose text it was first does not change that.
2. A page the repository no longer declares is kept, not deleted. CLAUDE.md §9: never delete without
   asking.
3. *Shown as out of date* means on the guide's contents page, which every run rewrites. A page that
   is not regenerated cannot show anything about itself.
4. *An internal address* is refused as an IPv4 literal outside the loopback and example ranges.
   What the rule cannot catch is stated in ADR-0065, *Where this promise ends*.
5. *Reaches that page at the next run* applies to a change in what the page says. A commit that
   changes nothing a page says leaves the page as it is. The page then still names the commit it
   was generated at, which remains true.
6. The wiki NEED-0021 asks for is private. Publishing the guides openly would be a statement under
   the project's name (M3.7), which nobody decided.

## 2. The evidence

- Issue #88, its sections "How it is verified" and "Where the boundary lies", derived from UC-13.6
  §2 and §3 on 2026-10-10.
- `tests/components/knowledge/test_guides.py`: rendering, refusal, the configured place, the
  content digest, and every state against a fake knowledge system — a page edited between the
  reading and the writing included.
- `tests/adapters/connectors/test_directory_connector.py`: the file a page becomes, the conflict, the
  repeat, the refused place.
- `tests/integration/test_guides_command.py`: both guides of this repository render at its commit,
  and `taktusctl guides publish` keeps a file edited by hand, prints its difference and shows it out
  of date.

## 3. What was considered

- **Write the guides on every merge, from CI.** Rejected: UC-13.6 asks for a process of Taktus with
  its steps and ledger entries, which is issue #198. A job of the repository's host would be a second
  place where the guides are made.
- **Report a hand edit and overwrite it.** Rejected: the person's text would be lost from where they
  wrote it, and UC-13.6 says it is not overwritten silently.
- **Delete a page the repository no longer declares.** Rejected: a delete is never made without
  asking (CLAUDE.md §9).

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public."* The scope is issue #88. The capability
`knowledge.pages` is new and breaks no published contract under `contracts/`. No limit or level
moves. The guides are written to a directory the operator names; nothing is published under the
project's name.
