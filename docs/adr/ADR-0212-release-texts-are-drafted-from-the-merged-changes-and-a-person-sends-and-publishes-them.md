# ADR-0212 — Release texts are drafted from the merged changes, and a person sends and publishes them

**Status:** accepted · extends ADR-0193 (the repository service's pull requests), ADR-0142
(outward messages) and ADR-0088 (a step that asks) · issues #438, #440, UC-03 B-8.01, B-8.08,
B-9.07

## Context

A release carries texts: a test plan, a changelog, the stores' "what's new", a newsletter and a
post on the website (UC-03 B-8.01, B-8.08, B-9.07). They are written from what the release
carries: the changes merged since the last one. Releasing them stays with a person; sending a
newsletter to the list and publishing a post are a person's acts at every level (UC-03 §4.8,
§4.9, §6 "mass sending").

The repository service lists closed pull requests, but its list states a merge as `merged_at`,
not as the `merged` its single reading gives. The website and the newsletter are each reached
through the most widely used product with a public API for it (ADR-0150): a site's REST API for
posts, and a mail-broadcast service's campaigns.

## Decision

### 1. The release's changes are a rule over the repository's own fields

`repository.pullrequests.list` gives each pull request `merged` from either field and
`merged_hours`, the whole hours since its merge. B-8.01, B-8.08 and B-9.07 keep, by the rule
`filter`, those merged within the hours the run names. A model writes the texts from their
titles alone, under fixed headings, and states no figure: the count of changes is the
repository's, put in by a template.

### 2. A draft is written where it is used, and the last act asks a person

B-8.01 writes the four drafts as one comment on the release pull request. B-8.08 drafts the post
on the website through `website.posts` and B-9.07 a campaign through `newsletter.broadcasts`,
each once a person confirmed it at level 2. Publishing the post and sending the campaign carry
`ask`: a decision request at every level. The newsletter's request names the number of
recipients as the service counts it. No recipient's address leaves the service.

| Capability | Operations | The mark |
|---|---|---|
| `website.posts` | `draft`, `read`, `publish` | the draft's slug carries the key's mark; a publish is marked by the post's status |
| `newsletter.broadcasts` | `draft`, `read`, `send` | the campaign's internal title carries the key's mark; a send is marked by the campaign's status |

## Alternatives

- **The changelog committed to the release branch.** It would write into the code the release
  carries before a person read it; a comment is read first and taken over by a person.
- **A segment of the audience proposed.** It needs the audience's fields, which name people;
  the process sends to the audience a person named.
- **A post published at level 3.** UC-03 sets B-8.08's target at level 2, publishing with a
  person.

## Consequences

- Connectors `wordpress` and `mailchimp`, their fakes, scenarios and images;
  `WEBSITE_TOKEN` and `NEWSLETTER_TOKEN` in `CREDENTIALS.md`.
- The repository connector's list carries `merged_hours`, and `merged` from `merged_at`.
- `blueprints/software-operations/processes/` gains B-8.01, B-8.08 and B-9.07.

## Where this promise ends

- **The changes are those merged within the hours given.** A pull request merged earlier and
  released late, or one merged into another branch, is counted by the hours alone.
- **Titles only.** A model reads the titles, not the code or the descriptions; a title that
  says little gives a draft that says little.
- **Links and search terms are not checked.** The post links nothing the model was given, and
  the terms are the business's own in the website's editor.
- **One audience, one site.** A newsletter to several audiences, or a post on several sites, is
  a run each.
- **A drafted post or campaign that a person rejects stays as a draft** in the website or the
  service until a person deletes it there.
