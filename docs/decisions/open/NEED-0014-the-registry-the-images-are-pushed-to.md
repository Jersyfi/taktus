# NEED-0014 — The registry the images are pushed to

**Kind:** action
**Raised in:** [#118](https://github.com/Jersyfi/taktus/pull/118)
**Issue:** [#114](https://github.com/Jersyfi/taktus/issues/114)
**Needed by:** 2026-10-20
**Foreseeable since:** [#118](https://github.com/Jersyfi/taktus/pull/118), which adds the workflow that builds the images on a release tag and pushes them to the registry a repository setting names

## 1. What is needed

One setting of this repository: the **container registry** the release images are pushed to,
as the repository variable `IMAGE_REGISTRY`. A container registry is the store the cluster pulls
its images from. With the variable set, every release tag builds three images — the control
plane, the reference worker and the coding worker — and pushes them there under the release's
version. Without it, a release tag builds nothing.

## 2. Why

The cluster cannot run Taktus from images built on a developer's machine: it pulls them from a
registry. The install on the cluster (#66) names the control plane's image in the chart
(`image.repository`, `image.tag`), and the cluster execution adapter (#65) names the coding
worker's. Both need the images to be there.

## 3. By when

**2026-10-20**, with the install (#66). If it is not set by then, the install waits: there is no
image the cluster can pull. A session may not set it: changing the repository's settings is
yours.

## 4. How to provide it

1. **Choose the registry.** Recommended: the repository service's own container registry,
   under your account. The workflow then pushes with its own token, and no credential is
   created at all.
2. **Choose whether the images are public.** Recommended: public. The repository is public,
   the images carry no secret (`deploy/docker/Dockerfile`), and the cluster then pulls without a
   pull secret. A private image needs a pull secret in both namespaces, named in the chart as
   `image.pullSecret`.
3. **Set the variable** — in the repository's settings under *Secrets and variables → Actions →
   Variables*, or in a terminal:

   ```bash
   gh variable set IMAGE_REGISTRY --body "<registry host>/<your account>"
   ```

4. **Say which processor the cluster's node has**, if it is not `x86_64`: set
   `IMAGE_PLATFORMS` to `linux/arm64`, or to `linux/amd64,linux/arm64` for both. Unset, the images
   are built for `linux/amd64`.
5. **Only for a registry other than the repository service's own:** a push credential that may
   write images to that one namespace and nothing else, as the repository secret
   `IMAGE_REGISTRY_TOKEN`, and the account it belongs to as the variable `IMAGE_REGISTRY_USER`:

   ```bash
   gh secret set IMAGE_REGISTRY_TOKEN     # prompts for the value; it is never on the command line
   gh variable set IMAGE_REGISTRY_USER --body "<the account>"
   ```

The images are first built at the next release tag. Cutting a release is yours (M3.6).

## 5. What it must never be

- **The variable is not written into this repository**, nor the registry's name: it is this
  deployment's own, and the repository is public. It lives in the repository's settings and in
  your private note.
- **A push credential is never a personal token with wider rights**, never pasted into a chat, a
  session, an issue or a pull request, and never committed. It goes into the repository secret
  of step 5 and nowhere else.

## 6. What happens next

Tell the session: **"NEED-0014: set."** The next release tag builds and pushes the three images;
the install (#66) names the control plane's in the chart.

## 7. How to confirm

`gh variable list` lists `IMAGE_REGISTRY` (and `IMAGE_PLATFORMS` where set). After the next
release tag, the run of the workflow `images` shows three build jobs, each green, and the
registry lists `taktus`, `taktus-worker-script` and `taktus-worker-coding` with that version.
