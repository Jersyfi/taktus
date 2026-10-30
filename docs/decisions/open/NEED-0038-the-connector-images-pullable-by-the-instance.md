# NEED-0038 — The connector images pullable by the instance

**Kind:** action
**Raised in:** the branch `concept/package-b` (package B, built in concept mode, DEC-0222), for issue #339
**Issue:** [#650](https://github.com/Jersyfi/taktus/issues/650)
**Needed by:** 2026-11-06
**Foreseeable since:** the branch `concept/package-b--images`, where every connector became an image of its own (ADR-0158)

## 1. What is needed

The twelve new images `taktus-connector-<name>` in the project's registry are public, as the
control plane's and the workers' images are (NEED-0014: "the images are public"). Each is a
package of its own in the registry, and a new package may start private.

## 2. Why

From package B on, the instance starts its repository and chat connectors from their own images
instead of the control plane's (ADR-0158). An image the instance cannot pull leaves those two
connectors' pods failing on the upgrade, and with them every process that reads an issue or
writes to the owner's channel.

## 3. By when

**2026-11-06**, and in any case before the first release candidate with package B is installed. If it is not done by then, the
session does not install that candidate; nothing else waits.

## 4. How to provide it

**Step 1 — check.** After the release candidate is tagged and its images are pushed, the session
checks each image with an anonymous pull. Where all twelve are public, this need is provided by
itself, and the session records that; nothing is asked of the owner.

**Step 2 — only where one is private.** Open the registry's page of that package (the
repository service's account, *Packages*, `taktus-connector-<name>`), *Package settings* →
*Change visibility* → *Public*, and confirm with the package's name. Repeat for every image the
session names in the issue.

## 5. What it must never be

- **Never an access token on the instance for pulling**: the images are public by the owner's
  answer to NEED-0014, and a pull secret would be one more credential to rotate.

## 6. What happens next

Write in the issue: **"NEED-0038 is provided."** The next session records it first, checks the
pull again, and installs the release candidate under the standing rule M1.25.

## 7. How to confirm

For each image, without signing in:

```sh
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  --header "Authorization: Bearer $(curl --silent 'https://ghcr.io/token?scope=repository:jersyfi/taktus-connector-github:pull' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')" \
  https://ghcr.io/v2/jersyfi/taktus-connector-github/tags/list
```

It prints `200`.
