# NEED-0008 — A public name for the Taktus instance

**Kind:** information
**Raised in:** [#40](https://github.com/Jersyfi/taktus/pull/40), which records the target and writes the deployment plan
**Issue:** [#42](https://github.com/Jersyfi/taktus/issues/42)
**Needed by:** 2026-10-20
**Foreseeable since:** [#40](https://github.com/Jersyfi/taktus/pull/40), the pull request that planned the deployment; raised the same day

## 1. What is needed

A hostname under which the deployed Taktus instance is reachable, pointing at the machine it
runs on, and a decision about whether it is served at the root of that name or under a path.
That is all: a name and, if you want one, a path prefix. No certificate — the platform issues
that itself — and no secret.

## 2. Why

Two things need it, and neither can be built against a guess.

- **The certificate.** The platform's certificate manager fetches a certificate for the name
  the instance's ingress declares. Without a name there is no ingress object, and without an
  ingress object the chart has a hole in it.
- **The webhook.** Taktus receives events from the repository — an issue opened, a comment, a
  pipeline finished — at `<name><prefix>/intake/<channel>`. The repository's webhook has to be
  pointed at that address, and the address has to exist before it can be pointed anywhere. It
  is also what turns the poll that took 64 % of the first live run's wall clock into an event
  (`docs/runs/first-run.md` §2).

It is `information` and not `access`: you are telling the deployment what it will be called,
not giving it anything.

## 3. By when

**2026-10-20**, with NEED-0007, so that the deployment pull request renders a chart with a real
ingress in it rather than a placeholder.

If it is not there by then: the chart is written with the ingress switched off and Taktus is
reachable only from inside the cluster. Nothing breaks; the webhook cannot be set up, the
instance keeps polling, and the deployment is proven for everything except the half that
matters for reacting to events.

## 4. How to provide it

1. **Choose the name.** A subdomain of a domain you already control is enough. Point it at the
   machine that runs the cluster — the same address the platform's ingress already answers on;
   an `A` record is all it takes, and if the machine already serves other names on that address
   the record is the only new thing.
2. **Decide root or sub-path.** At the root of the name, Taktus serves `/intake/...` and the
   rest of its interface directly; under a sub-path, everything moves beneath it and the
   instance is told the prefix. The root is simpler and is the recommendation unless the name
   is shared with something else.
3. **Say whether the certificate should come from the platform's usual issuer** — the one that
   already issues for the other name on that machine — or from somewhere else. If it is the
   usual one, there is nothing to do beyond the name: the chart names the issuer and the
   certificate appears.
4. **Write the answer down where the deployment's own configuration lives** — the private note
   beside the platform's other details, not this repository. Three lines is the whole answer:
   the name, root or prefix, and the issuer.

**Not yet, and deliberately:** the webhook itself. Setting it up needs a signing secret, which
is its own need and will be raised the moment this name exists, with the steps — the secret is
set at the repository and in the instance in one move, and the connector refuses every delivery
it cannot verify against it.

## 5. What it must never be

- **Never in this repository.** A deployment's hostname is that deployment's own business and
  this repository is public (`CREDENTIALS.md`: deployment-specific names belong in the
  operator's private configuration). The chart holds the *key* `ingress.host`; the value is
  yours.
- **Never pasted into a chat or a session as something to remember.** Put it in the private
  note and tell the session where the note is; it reads it there.
- **Never a name that already serves something else**, unless you have chosen the sub-path
  option on purpose and know what else answers on it.
- **Never an address instead of a name.** A certificate cannot be issued for a bare address,
  and the webhook would have to be repointed the day the machine moves.

Where it goes instead: the private note that already describes the platform.

## 6. What happens next

Tell the session: **"NEED-0008 is provided; the name is in the note."** The deployment pull
request then renders the ingress against it, the certificate is issued on the first install,
and the webhook's own need is raised with the address it will point at.

## 7. How to confirm

Without revealing anything but what is public anyway — the name resolves to the machine, and
the platform answers on it:

```bash
dig +short <the name>
```

prints the machine's address; and

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://<the name>/
```

answers at all — `404` is a perfectly good answer before Taktus is installed, and means the
name reaches the platform's ingress. After the install the same command answers from Taktus.
