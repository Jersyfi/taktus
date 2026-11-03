# `deploy/images/` — what every published image is held to

The images `.github/workflows/images.yml` publishes are scanned before they carry a tag, signed
without a key, and recorded by digest (ADR-0173). This directory holds what the scan reads.

| File | What it is |
|---|---|
| `grype.yaml` | the vulnerability scanner's configuration. `tools/scan_image.sh` passes it; the severity the scan fails on — `high` and above, where a fixed version exists — is in that script. Its `ignore` list is the one place a finding is set aside: each entry names one vulnerability and a reason naming the `gate-weakened` notice that records it, and `tests/governance/test_image_workflow.py` fails an entry without either |

## Scanning an image by hand

```
make image-tools                                       # the pinned grype and cosign, into .tools/bin
tools/scan_image.sh <registry>/<image>@sha256:<digest> [linux/amd64,linux/arm64]
```

The image is read from its registry, once per platform. Exit 0: no fixed vulnerability of
severity `high` or above. A finding without a fix is printed and does not fail. The scan needs
no Taktus and no credential beyond the registry's own login, if it is private.

## Verifying a signature by hand

The signature binds the digest to this repository's workflow and the ref it ran on — `main` or
a version tag. There is no key to compare with; the certificate names the workflow:

```
cosign verify <registry>/taktus@sha256:<digest> \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/<owner>/<repository>/\.github/workflows/images\.yml@refs/(heads/main|tags/v.+)$'
```

## When an image fails its scan

Its digest stays in the registry without a tag and without a signature; nothing pulls it by
name. The way on is one of three, in this order: a new build, which pulls the base image fresh;
a change that moves the vulnerable package to its fixed version; or an entry in `grype.yaml`
with its notice, when the finding does not reach Taktus.
