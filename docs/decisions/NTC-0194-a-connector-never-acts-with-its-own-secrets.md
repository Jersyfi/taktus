# NTC-0194 — A connector never acts with its own secrets

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** issue [#267](https://github.com/Jersyfi/taktus/issues/267), in the pull request that closes it

## 1. What was decided

1. **The repository connector and the chat connector never act with a secret they hold for
   themselves.** A call whose credential reference names the app's private key, the webhook
   secret or the chat's signing secret — by its name or by the file that holds it — is treated as
   a call without a credential and ends `unauthenticated`. Before, the connector read the file the
   name pointed at and used its content as the call's bearer token: on 2026-10-12 a scenario that
   named the app's key made the repository connector put the private key into an
   `Authorization` header, which the HTTP library refused locally, so it never left the machine.
2. **A transport fault is named by the error's type, never by its text.** The HTTP library's
   message quoted the refused header, and the connector returned it as the error's detail: the key
   appeared in the error, in the session's output and in the conformance evidence the instance
   stored. The wiki connector already named the type alone.
3. **C-04 looks for a credential in every form an error can quote it**: in clear, in base64, with
   its line breaks escaped, and by each of its lines long enough to be its own. Before, a key of
   several lines quoted with escaped line breaks passed.

## 2. The evidence

- `tests/adapters/connectors/test_transport_faults.py`: a transport whose error quotes a made-up
  credential leaves it in no error of either connector; a call naming the connector's own secret,
  by name or by path, acts with nothing, and one naming its own credential still acts with it;
  C-04 fails on a key quoted with escaped line breaks.
- The conformance suites of the reference connector, both modes, its fault meta-test and the chat
  connector's: unchanged and green.

## 3. What was considered

- **Masking the text instead of dropping it.** A mask needs every secret's value at the place of
  the error; the type names the fault well enough, and the wiki connector already did so.
- **Refusing the call with `invalid`.** A call that names a secret the connector holds for itself
  has no credential the connector may use; `unauthenticated` says exactly that, and it is what a
  call without a credential already ends with (C-03).

## 4. Which entry permits it

M2.4: what the connectors do changes inside their contract — no published contract breaks, a
check becomes stricter, no limit or level moves, nothing is published. The rotation of the key
that appeared is the owner's (`CREDENTIALS.md`: rotate first, clean up second).
