"""The app stores connector's configuration: both stores' addresses, shared by every operation."""

from __future__ import annotations

from dataclasses import dataclass

APP_STORE = "https://api.appstoreconnect.apple.com"
PLAY = "https://androidpublisher.googleapis.com"


@dataclass(frozen=True)
class Config:
    app_store_target: str = APP_STORE
    """The App Store Connect API's address; the store's own, or a fake's."""
    play_target: str = PLAY
    """The Google Play Developer API's address; the store's own, or a fake's."""
    timeout: float = 30.0
    blind: bool = False
    """Fault C-05 only: a reply to a review is written without reading the response in place."""
