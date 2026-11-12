"""Every operation the connector serves: the mail connector's (`messages.py`) and the
newsletter connector's (`broadcasts.py`), under their own names."""

from __future__ import annotations

from taktus_connectors.resend import broadcasts, messages
from taktus_connectors.serving import Operation

OPERATIONS: dict[str, Operation] = {**messages.OPERATIONS, **broadcasts.OPERATIONS}
