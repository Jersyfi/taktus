# The app stores connector — App Store Connect and Google Play

`stores.beta` and `stores.releases` over the two stores a mobile app is distributed through: the
**App Store Connect API** for iOS and the **Google Play Developer API** (`androidpublisher` v3)
for Android. Each call names its `platform`, `ios` or `android`, and is answered by that
platform's store. This directory, this file and the configuration that points at it are the only
places in the repository that name the products. Everywhere else it is `stores.beta` and
`stores.releases` (ADR-0210).

```
uv run python -m taktus_connectors.appstores --port 9140
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.
`--app-store-target` (default `https://api.appstoreconnect.apple.com`) and `--play-target`
(default `https://androidpublisher.googleapis.com`) are the stores' addresses; `--target` sets
both, as the fake under `tests/fakes/app_stores_service.py` serves both. Added to an instance by
one entry of `TAKTUS_CONNECTORS` per capability, both at the same address.

The documentation followed:

- App Store Connect API, <https://developer.apple.com/documentation/appstoreconnectapi>: *List
  Builds* (`GET /v1/builds`), *Get All Build IDs in a Beta Group* and *Add Builds to a Beta
  Group* (`/v1/betaGroups/{id}/relationships/builds`), *List All Beta Feedback Screenshot
  Submissions* and *Crash Submissions for an App*, *List All App Store Versions for an App*,
  *Read App Store Version Information*, *Modify an App Store Version Phased Release*
  (`PhasedReleaseState`), *List Review Submissions*, *Create a Review Submission*, *Create a
  Review Submission Item*, *Modify a Review Submission*, `AppVersionState`; *Generating Tokens
  for API Requests*.
- Google Play Developer API, <https://developers.google.com/android-publisher/api-ref/rest>:
  `edits.insert`, `edits.delete`, `edits.commit`, `edits.bundles.list`, `edits.tracks.get` and
  `edits.tracks.update` with the `Track` and `Release` resources and their `Status`; *Using
  OAuth 2.0 for Server to Server Applications*.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `stores.beta.builds` | read | — | `platform`, `app` (the App Store Connect app's identifier, or the package name), `limit` (default 20, at most 200): `builds`, newest first, each `id`, `version` (the marketing version, iOS only), `number` (build number or version code), `state` (the store's own word: `processingState`, or `valid`), `uploaded`; `complete`. On Android an edit is opened, its bundles read, and the edit deleted |
| `stores.beta.distribute` | write | marked | `platform`, `app`, `build` (a build's identifier, or a version code), `group` (a beta group's identifier, or a track's name such as `internal`): the build added to the group, or released `completed` on the track and the edit committed. **iOS: the build in the group is its own mark**: a repeat that finds it there changes nothing and reports `replayed`. **Android: the release's `name` is the key's mark**, found on the track by a repeat |
| `stores.beta.feedback` | read | — | `platform` `ios`, `app`, `limit` (default 50): `feedback`, newest first, each `id`, `kind` (`screenshot` or `crash`), `created`, `comment`, `build`. Only these fields are asked for: never the tester, their address, the device's settings or the crash log. The Play Developer API publishes no tester feedback, so `android` is `invalid` |
| `stores.releases.read` | read | — | `platform`, `app`, `version` (optional: an App Store version's identifier, else the newest; on Android a version code, which on no release of `production` reads `review` `preparing`: still to submit): `version`, `id`, `state` (the store's word: `appVersionState`, or a release's `status`), `review` (`preparing`, `waiting`, `in_review`, `rejected`, `approved`, `live` or `other`), `phased` (the iOS phased release's `state` and `day`), `fraction` (the Android `userFraction`, 1 once completed), `rolled_out`. On Android the release read is the staged one of the `production` track, else its completed one. **The Play Developer API publishes no review state**: `review` is always `other` there |
| `stores.releases.raise` | write | marked | `platform`, `app`, `fraction` (above 0, at most 1). Android: the staged release of `production` set to that `userFraction`, or `completed` at 1. iOS: the phased release of the newest live version made `ACTIVE`, or `COMPLETE` at 1; the store follows its own seven-day schedule and takes no fraction, so `fraction` is `null`. **The state is its own mark** |
| `stores.releases.halt` | write | marked | `platform`, `app`: Android's staged release `halted`, iOS's phased release `PAUSED`. No staged rollout in progress is `conflict`. **The state is its own mark** |
| `stores.releases.submit` | write | marked | `platform`, `app`, `version` (an App Store version's identifier, or a version code), `fraction` (Android only, optional). iOS: an unsubmitted review submission of the app is found or created, the version added as its item, and `submitted` set. Android: the version code released on `production`, `inProgress` at the fraction or `completed`, as a release whose `name` is the key's mark, and the edit committed; a version code already on production under another name is `conflict`. **iOS: a version already waiting for review or further is its own mark** |

**The mark.** A Play release that a write makes carries as its `name` the mark `taktus-` and the
first 16 hexadecimal digits of the SHA-256 of the idempotency key, which never leaves Taktus. A
release's name is shown in the Play Console only, never to the app's users. A repeat finds the
release with the mark on the track, and nothing is written again.

App Store Connect has no field a write could put the key into, and neither store has one for a
staged rollout's fraction or halt. There **the state a write leaves is its own mark**. **Weaker
than a key, and stated so**: a repeat after somebody else made the same state reports replayed
too (as `deployment.workloads.scale`, ADR-0097). A version a person submitted by hand is
therefore not submitted again. The conformance suite judges the repeat on the Android
`stores.beta.distribute`, whose new key acts again; `tests/adapters/connectors/
test_app_stores_connector.py` proves every other repeat against the fake.

Every Android operation works in an edit: a reading deletes it, a change commits it, a change
that finds nothing to do deletes it, and a failure deletes it as far as the store answers. A
timed-out change is `unknown` with effect `unknown`; a repeat reads the state again.
Consumption is counted in `quota` units named `requests`, the token exchange among them.

## Credentials

One, `STORES_KEY`: a JSON object with up to two members, each the key of the requesting
identity at one store (`CREDENTIALS.md`).

- `ios`: an App Store Connect API key, `{"issuer_id", "key_id", "private_key"}`, the private key
  the `.p8` file's PEM. A team key with the role *App Manager* reads builds, versions and
  feedback, manages beta groups, the phased release and review submissions. Every call signs a
  token of twenty minutes.
- `android`: a Google service account key as Google issues it, of an account invited to the
  app in the Play Console with *Release to testing tracks*, *Release to production, exclude
  devices, and use Play App Signing* and *View app information*. Every call exchanges a signed
  assertion at the key's `token_uri` for an access token of the scope `androidpublisher`.

A call for a platform whose member is absent is `unauthenticated`. The value is read at the
moment of the call from the file `TAKTUS_CREDENTIAL_STORES_KEY_FILE` names, and neither key nor
token is ever logged. The connector has no key of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9140/mcp --scenario connectors/taktus_connectors/appstores/scenario.json
```

[`scenario.json`](scenario.json) lists the builds of an iOS app, gives an Android build to the
`internal` track twice under one key and once under another, and asks for a platform the
connector does not serve. Against the real stores it releases to a test track: point it at a
test app.
