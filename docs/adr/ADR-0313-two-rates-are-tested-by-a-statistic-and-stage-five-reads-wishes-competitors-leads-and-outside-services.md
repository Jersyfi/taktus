# ADR-0313 — Two rates are tested by a statistic, and stage five reads wishes, competitors, leads and outside services

**Status:** accepted · extends ADR-0151, ADR-0207, ADR-0209, ADR-0213, ADR-0218 · UC-03 (B-6.07, B-9.04, B-9.09, B-9.10, B-10.02)

## Context

Stage 5 of UC-03 lists processes the blueprint `software-operations` did not have. Five of them
can be built over capabilities the product already serves:

- **B-6.07 Price experiments** asks for "significance by `statistics`". The one built-in
  statistic, `deviation` (ADR-0151), judges a day against a median. Nothing tested whether two
  rates differ beyond chance, so the blueprint's README named it as not built.
- **B-9.04** groups feature wishes. The feedback portal's posts are read (`feedback.posts`,
  ADR-0207).
- **B-9.10** watches competitors, and **B-9.09** researches a business that enquired. Both read
  public pages. The browser worker opens pages (`browser.check`, ADR-0218).
- **B-10.02** finds a new outside service in a pull request. The repository service lists a pull
  request's changed files with their patches (ADR-0194).

## Decision

### 1. A second statistic: the significance of two rates

`statistics` steps choose their statistic by `statistic`. Beside `deviation` stands
`significance`, `SignificanceStatistic` in the run component's work model and
`statistics.significance` in its domain service.

- **What it reads.** A report's rows, usually a reference to an analytics reading. Each row
  names its variant, its event and its count at paths the step states as lists of keys. The
  counts of the `exposure` event are a variant's trials. The counts of the `conversion` event
  are its successes. Rows of the same variant and event are summed.
- **What it computes.** The two-sided test of two proportions with the pooled rate. The rates,
  their difference and `z` are computed in decimal arithmetic.
- **How it decides.** `significant` holds when the absolute value of `z` is at least the fixed
  critical value of the level `alpha`. The level is one of 0.10, 0.05, 0.01 and 0.001, each with
  its critical value to sixteen decimals. No approximation enters the decision. The same rows
  always give the same decision, which makes the result admissible for `exact`.
- **What it reports beside.** The p-value, rounded to six decimals. It is information and
  decides nothing.
- **What fails the step.** Rows that are not a list, a row without a stated path, a count that
  is not a whole number of events, a variant without exposures, or more conversions than
  exposures. Two rates that cannot differ, both nothing or both everything, give no `z` and are
  not significant.

### 2. B-6.07 reads the experiment from the analytics service

The run reads, through `analytics.reports`, the event count per variant and event over the
experiment's days. The variant is a dimension the business registered in its analytics. The
statistic runs only on a report that is complete and neither sampled nor thresholded. A model
writes a recommendation from the statistic's result. The process changes nothing and starts at
level 1. Changing a price stays with a person (UC-03 §6).

### 3. B-9.04 keeps the unplaced wishes by rule and groups them by a model

The rule `filter` keeps the posts whose status is `open` or `under review`, ordered by the
portal's vote count. A model groups them into clusters, each naming its posts. The votes stay
the portal's. The process starts at level 1.

### 4. B-9.10 and B-9.09 read public pages through the browser worker

Each page is opened on the hosts the run names, the frame's allowed hosts. The worker's report
gives a page's status, its title, and which expected texts it shows. It gives no other text of
the page.

- **B-9.10** carries, per competitor page, the texts the business last saw there. A page that
  no longer shows one of them changed, by the report's own verdict. A model summarises the
  changed pages from the report alone. The worker's assignment is an act, so the process starts
  at level 2.
- **B-9.09** reads the enquiry, finds the sender in `crm.contacts` scoped to the case, and opens
  the company's site. A model drafts an offer without a price. The offer is sent through
  `mail.messages` under the tenant's message frame (UC-7.6). The send step asks a person at every
  level. A rule holds a draft that states an amount of money. The price and sending stay with a
  person.

### 5. B-10.02 finds a new host in a pull request's added lines

The pull request's files are read with their patches and composed into one text. The rule
`extract` takes every host an added line names after `http://` or `https://`. It leaves out the
hosts of the services the tenant names as known. A host left is filed as one issue per pull
request, once, under the mark `outside-services:pr-<number>`. Filing leaves the system, so the
process starts at level 2.

## Alternatives

- **A p-value as the decision.** It needs the normal distribution's tail in floating point,
  whose last digits can differ between platforms. A fixed critical value decides the same
  everywhere.
- **A free significance level.** It would need the critical value computed at the run.
  Four levels cover the common practice.
- **A model judging whether two rates differ.** A figure held exact may not come from a model
  (CLAUDE.md §4).
- **The page's text from the browser worker.** The worker reports no page text on purpose: a page
  may hold anything. Extending it is the worker's change, not this one's.
- **Every new dependency as an outside service in B-10.02.** Most dependencies reach no outside
  host. Filing each would bury the few that do.

## Consequences

- A `statistics` step may name `significance`. A bundle that named another word is refused
  under `statistic`, as before.
- The analytics fake carries an event-scoped variant dimension and a test-only lift of one
  variant's purchases (`tests/fakes/analytics_service.py`).
- Five bundles join `blueprints/software-operations/processes/` and `blueprint.yaml`, each run
  against fakes in `tests/composition/test_software_operations_stage5.py`.

## Where this promise ends

- **The test is the two-proportion test only.** It assumes independent trials, large enough
  counts and one comparison. It does not correct for looking at an experiment repeatedly, for
  several variants or for several metrics. A person who reads the result decides with that in
  mind.
- **The counts are the analytics service's.** An event the business's product does not record,
  or records under the wrong variant, is counted as recorded.
- **B-9.10 sees only the texts it was given.** A competitor's change elsewhere on a page, or on a
  page the run does not name, is not seen. A page that renders a known text differently counts as
  changed.
- **B-9.09 reads no page text and no company record.** The customer system's search gives
  whether the sender is a contact and at which stage. The site gives its status and title. The
  offer carries nothing more than these and the enquiry.
- **B-10.02 sees only addresses written in the change.** A service a library reaches without its
  address in the change, and a host written without its scheme, are not found. The record of
  processing is the business's document; the process files an issue and changes no record.
- **Nothing here concludes an agreement, sets a price or sends without a person.**
