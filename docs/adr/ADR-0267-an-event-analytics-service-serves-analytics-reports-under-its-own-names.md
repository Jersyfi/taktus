# ADR-0267 — An event analytics service serves `analytics.reports` under its own names

**Status:** accepted · extends ADR-0213 (figures without personal fields) and ADR-0150
(connectors for the systems a business names) · UC-03 §4.9, DEC-0228

## Context

`analytics.reports` reads aggregates of one source without a personal field (ADR-0213). Its one
connector reads a web property, whose names are a web analytics API's: active users, new users,
sessions, the ISO week. A software product is more often measured by the events it tracks. The
most widely used event analytics service publishes a Query API that counts named events per
day, week or month, and the users who did them. It knows no session and no new user.

## Decision

### 1. One operation, the source's own names

A connector `mixpanel` serves `analytics.reports.run` with the operation's input fields and its
output, so that the steps that read rows read them unchanged. The names inside the fields are the
service's: the metrics `general`, `unique` and `average`, the dimensions `day`, `week`, `month`
and `event`, and a required list of `events`. A name the service has no counterpart for is
refused as `invalid` before the service is asked. Nothing is mapped onto a figure it is not.

### 2. Only what adds up

The users of two days or two events overlap, so `unique` and `average` need a time dimension and
one event or the dimension `event`. The endpoint has no breakdown by a property, and no
profile or person's activity is asked for.

### 3. B-9.03 gains a version for events

`B-9.03-weekly-trends-events.yaml`, of the same process `b-9-03`, reads one activity event the
tenant names, by week, its users and its count. A tenant registers the version of its service,
as ADR-0211 §2 does for B-8.05.

## Alternatives

- **The service's names translated to the web property's.** `unique` users of one event are not
  active users, and sessions do not exist there: a translation would report a figure the service
  never gave.
- **The segmentation report.** Its reference marks it as in maintenance and it has no weekly
  unit.
- **A saved report.** Its content is defined by a person in the service, not by the process.

## Consequences

- Connector `mixpanel`, its fake `tests/fakes/product_analytics_service.py`, scenario and image;
  `ANALYTICS_KEY` names it in `CREDENTIALS.md`, a service account as `<username>:<secret>`.
- B-9.03's event version, proven in `tests/composition/test_software_operations_connectors2.py`.

## Where this promise ends

- **The original B-9.03 does not run on it.** Its names are the web property's; the event
  version does.
- **The service may filter what a service account sees.** A project with classified data answers
  filtered figures without saying so; `sampled`, `thresholded` and `other_row` are always
  `false`, because the endpoint states none of them.
- **An event's name is the business's.** That it carries no personal data is the business's to
  keep.
- **The fake follows the published reference.** Its week and month keys are the fake's reading
  of a reference that shows only daily keys; nothing was run against the service.
