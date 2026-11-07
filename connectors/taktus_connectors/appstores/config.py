"""The app stores connector's configuration: both stores' addresses, shared by every operation."""

from __future__ import annotations

from dataclasses import dataclass

APP_STORE = "https://api.appstoreconnect.apple.com"
PLAY = "https://androidpublisher.googleapis.com"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — an address, not a secret


@dataclass(frozen=True)
class Config:
    app_store_target: str = APP_STORE
    """The App Store Connect API's address; the store's own, or a fake's."""
    play_target: str = PLAY
    """The Google Play Developer API's address; the store's own, or a fake's."""
    timeout: float = 30.0
    blind: bool = False
    """Fault C-05 only: a reply to a review is written without reading the response in place."""
    token_endpoint: str = ""
    """Where the Android key is exchanged, where neither Google's nor `<play_target>/token`."""

    def token(self) -> str:
        """Google's token endpoint while the Play API is Google's own; else `<play_target>/token`,
        where a stand-in serves both; or the endpoint configured."""
        if self.token_endpoint:
            return self.token_endpoint.rstrip("/")
        base = self.play_target.rstrip("/")
        return GOOGLE_TOKEN if base == PLAY else f"{base}/token"
