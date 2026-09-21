# Open requests

One file per request. A **decision request**, `DEC-NNNN-<slug>.md`, in the shape of
[../TEMPLATE.md](../TEMPLATE.md), has a matching GitHub issue labelled `decision-request`. A
**needs request**, `NEED-NNNN-<slug>.md`, in the shape of [../TEMPLATE-NEED.md](../TEMPLATE-NEED.md),
has a matching issue labelled `needs-owner`. Both are assigned to the owner. A file leaves this
directory in the same commit that writes its record into [../](../README.md).

While a file with `**Category:** BLOCKING` is here, the pull request that raised it stays a draft.
An open need keeps no pull request a draft; it stays listed in [../../status.md](../../status.md)
until it is provided.
