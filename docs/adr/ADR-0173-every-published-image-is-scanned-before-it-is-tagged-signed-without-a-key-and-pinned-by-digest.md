# ADR-0173 — Every published image is scanned before it is tagged, signed without a key, and pinned by digest

**Status:** accepted · extends ADR-0158 (every connector is an image of its own), ADR-0087 (the
backup's image) and ADR-0020 (the development instance runs `main`) · bounded by ADR-0013 D
(Taktus does not put itself into production) and M3.6 (a release process is the owner's) ·
issue #347, DEC-0187

## Context

`.github/workflows/images.yml` built every image on a version tag and pushed it under that tag.
The DevOps review found three gaps (`docs/research/2026-10-12-devops-review.md`, K5):

- **No scan.** An image could carry a package with a known, fixed vulnerability, and nothing
  said so before an operator pulled it.
- **No signature.** An operator could not tell an image the workflow built from one somebody
  pushed under the same name.
- **No digest.** A tag names an image only as long as nobody pushes the tag again. The chart
  refused `latest`, but it could not refer to an image by the one name that cannot move: its
  digest. A digest is the SHA-256 of the image's manifest.

A fourth gap is the development instance's. ADR-0020 says it runs `main`. Images were built
only on a version tag, so there was no image of `main` to run.

## Decision

### 1. One workflow, two triggers

`images.yml` runs on a version tag `v*` and on a push to `main`. A version tag publishes every
image under the version. A push to `main` publishes every image under the full commit hash, the
tag the development instance runs. The set of images is the same for both. A push to `main`
that a newer push overtakes is cancelled, so that the registry holds no half-built commit.

### 2. Nothing carries a tag until its scan passed

Each image is built and pushed **by digest only**, without a tag. The scanner then reads that
digest from the registry, once per platform built. Only when the scan passes does the workflow
put the tag on the digest and sign it. An image that fails its scan stays an untagged,
unsigned digest. No chart and no person pulls it by name.

The scanner is grype, an open-source scanner that matches an image's packages against public
vulnerability databases. It is pinned with its SHA-256 in `tools/install_image_tools.sh`, the
way helm is pinned. No action of a third party installs it.

**The scan fails on a vulnerability of severity `high` or `critical` for which a fixed version
exists.** A finding without a fix is reported and does not fail: the image could not be built
without it, and the next build takes the fix when it appears. Every build pulls its base image
fresh, so a fix published upstream reaches the next build.

`tools/scan_image.sh` runs the scan. The workflow calls it, and a person can run it by hand.

### 3. An exception is written down, with a reason

`deploy/images/grype.yaml` is the scanner's configuration. Its `ignore` list is the one place a
finding can be set aside. Every entry names one vulnerability and a reason. A governance test
fails an entry without a reason. Setting a finding aside is a `gate-weakened` notice
(CLAUDE.md §9), because it weakens what the scan holds.

### 4. The scanner proves it can fail

Before any image is built, a job scans a known-vulnerable image: `alpine:3.10.0`, pinned by its
digest. It has fixed critical vulnerabilities in `apk-tools` and `musl`. The job passes only
when that scan **fails on findings**. When the scan passes, or stops with an error instead of
findings, the job fails, and nothing is built. A scanner whose database did not load would
otherwise pass every image. The job publishes nothing and runs without the registry variable.

### 5. Signed without a key

The workflow signs each digest with cosign, a tool of the open-source Sigstore project, in
keyless mode. The workflow asks the repository service for a short-lived identity token
(`id-token: write`). Sigstore's certificate authority issues a certificate for that identity,
valid for minutes. The signature and the certificate are recorded in Sigstore's public
transparency log. **There is no signing key to store, rotate or leak, and no secret value.**

The certificate names the workflow file and the ref it ran on. An operator verifies an image
by those two, not by a key (`deploy/k8s/README.md` §3):

```
cosign verify <registry>/taktus@sha256:<digest> \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/<owner>/<repository>/\.github/workflows/images\.yml@refs/(heads/main|tags/v.+)$'
```

### 6. The digest is recorded

Each build reports its digest. A last job, `record`, gathers them through
`tools/image_digests.py` into two files, kept as the run's artefact and printed in its summary:

- `images.json`: every image with its repository, tag and digest.
- `digests.values.yaml`: the chart's values that pin every image the chart derives from the
  release, ready to pass to `helm upgrade -f`.

### 7. The chart refers to an image by digest

Every image value of the chart takes a digest beside its tag. `image.digest`,
`backup.image.digest`, `database.image.digest` and `connectors.digests.<name>` pin the images
the chart names by parts. An image given as one reference — `execution.image`, a worker's
image, the egress proxy's, a further connector's — may end in `@sha256:<digest>`. A pinned image
renders as `<repository>:<tag>@sha256:<digest>`. The tag stays for a reader; the container
runtime pulls the digest.

`images.requireDigest: true` fails the render of any image without a digest. It is off by
default, so that an install that worked before keeps working.

The chart's tag rule admits the commit tag of a `main` image: forty lowercase hexadecimal
characters. A commit hash names one commit and is never pushed twice.

## Alternatives

- **Scan after pushing the tag.** Simpler, but a vulnerable image is pullable by its tag until a
  person removes it. Refused.
- **Build locally, scan, then push.** A multi-platform build cannot be loaded into the local
  engine; only one platform would be scanned. Refused for the digest-first push, which scans
  each platform.
- **Trivy, or a marketplace action for the scan.** Trivy is an equal scanner. A marketplace
  action is code of a third party that can change under its tag, and it would run in the job
  that signs. The decision that matters is pinning the binary by its hash. Grype is the one
  chosen; replacing it is a change to two scripts.
- **A signing key in a repository secret.** It must be stored, rotated and protected, and it
  outlives the run that used it. Keyless signing needs none of that. Refused.
- **Failing on every severity, or on findings without a fix.** Every Debian-based image carries
  low findings and findings no one has fixed; the scan would always fail, and an always-failing
  gate is switched off. Refused.
- **Enforcing signatures in the cluster.** That needs an admission controller, a cluster-wide
  object the deployment identity may not create (`deploy/k8s/README.md` §1). Left to the
  operator.

## Consequences

- A release or a `main` build whose image has a fixed high or critical vulnerability publishes
  no tag for it. The fix is a new build, a base image bump or a recorded exception.
- Every push to `main` builds every image once more. It runs only where `IMAGE_REGISTRY` is set
  (NEED-0014), and a newer push cancels the older build.
- The workflow needs `id-token: write` in the job that signs. It needs no other permission than
  before, and no secret.

## Where this promise ends

- **The scan knows what the databases know.** A vulnerability not yet published, or in a
  package the scanner does not recognise, passes. The scan is a floor, not a proof of safety.
- **A finding without a fix does not fail the build.** It is visible in the scan's output only.
- **The scan runs when an image is built.** A vulnerability published after the build is not
  found in an image already pulled; a rebuild finds it. A scheduled rescan of published images
  is not promised here.
- **The signature says who built the image, not that it is good.** It binds the digest to this
  repository's workflow and ref. It says nothing about the code at that ref.
- **Verifying the signature is the operator's.** The chart does not check signatures, and no
  admission policy is shipped.
- **A digest pins what the chart renders.** An image a worker starts at run time is pinned only
  when its reference in the values carries a digest.
- **Not a release process.** Choosing a version, writing release notes, and putting an image
  into operation stay outside this workflow (M3.6, ADR-0013 D). The `main` image is built for
  the development instance; nothing here deploys it.
- **The proof image can stop proving.** Should the databases ever drop the findings of
  `alpine:3.10.0`, the proof job fails, and a person names another known-vulnerable image.
