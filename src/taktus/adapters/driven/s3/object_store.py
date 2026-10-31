"""Artifact bytes as keys of one bucket of an S3-compatible store (ADR-0165 §1).

An object is the key `<prefix>/<hex>`, addressed path-style: `<endpoint>/<bucket>/<key>`. Every
request is signed with the interface's signature version 4, written here on the HTTP client the
control plane already has, so that the store adds no library (ADR-0002). Two requests are used:
put and get of one key. Neither the credential's secret nor a signature is ever logged; an
error names the status and the store's error code alone.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from taktus.adapters.driven.memory.object_store import (
    DEFAULT_CACHE_BYTES,
    ObjectCache,
    digest_of,
    verified,
)
from taktus.ports.configuration import Secret
from taktus.ports.objectstore import ObjectStoreUnavailable
from taktus.shared.v1 import Digest

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"
DEFAULT_REGION = "us-east-1"
_SIGNED = ("host", "x-amz-content-sha256", "x-amz-date")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_CODE = re.compile(rb"<Code>([A-Za-z0-9.]{1,64})</Code>")


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def sign(
    *,
    method: str,
    url: str,
    payload_hash: str,
    access_key_id: str,
    secret_key: str,
    region: str,
    now: datetime,
) -> dict[str, str]:
    """The headers that sign one request without a query string, by signature version 4: the
    canonical request over method, path, the signed headers and the payload's hash; the string
    to sign over the time, the scope and that request's hash; the key derived from the secret
    through date, region, service and `aws4_request`."""
    parts = urlsplit(url)
    host = parts.netloc
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    values = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": stamp}
    canonical = "\n".join(
        [
            method,
            parts.path or "/",
            "",
            "".join(f"{name}:{values[name]}\n" for name in _SIGNED),
            ";".join(_SIGNED),
            payload_hash,
        ]
    )
    scope = f"{day}/{region}/{SERVICE}/aws4_request"
    to_sign = "\n".join([ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(
        _hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), day), region), SERVICE), "aws4_request"
    )
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": stamp,
        "Authorization": (
            f"{ALGORITHM} Credential={access_key_id}/{scope}, "
            f"SignedHeaders={';'.join(_SIGNED)}, Signature={signature}"
        ),
    }


def _error(response: httpx.Response) -> str:
    found = _CODE.search(response.content[:4096])
    code = found.group(1).decode() if found else "no error code"
    return f"status {response.status_code} ({code})"


class S3ObjectStore:
    """Bytes by digest in one bucket. Memory holds a cache of at most `cache_bytes` bytes, as
    the filesystem adapter does (#311). A key that is not there reads as None; bytes that do
    not hash to their key read as None and are logged; any other answer, and a store that
    cannot be reached, raise `ObjectStoreUnavailable`."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: Secret,
        secret_key: Secret,
        prefix: str = "",
        region: str = DEFAULT_REGION,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("the endpoint must be an http(s) URL")
        if not bucket:
            raise ValueError("a bucket is required")
        self._base = endpoint.rstrip("/") + "/" + quote(bucket, safe="")
        self._prefix = "/".join(quote(p, safe="-_.~") for p in prefix.strip("/").split("/") if p)
        self._access_key_id = access_key_id
        self._secret_key = secret_key
        self._region = region or DEFAULT_REGION
        self._cache = ObjectCache(cache_bytes)
        self._now = now
        self._timeout = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def cached_bytes(self) -> int:
        return self._cache.size

    def _url(self, digest: Digest) -> str:
        name = digest.removeprefix("sha256:")
        return f"{self._base}/{self._prefix}/{name}" if self._prefix else f"{self._base}/{name}"

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, transport=self._transport)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _send(self, method: str, url: str, content: bytes) -> httpx.Response:
        headers: Mapping[str, str] = sign(
            method=method,
            url=url,
            payload_hash=hashlib.sha256(content).hexdigest(),
            access_key_id=self._access_key_id.reveal(),
            secret_key=self._secret_key.reveal(),
            region=self._region,
            now=self._now(),
        )
        try:
            return await self._http().request(method, url, content=content, headers=headers)
        except httpx.HTTPError as error:
            raise ObjectStoreUnavailable(
                f"the object store could not be reached: {type(error).__name__}"
            ) from None

    async def put(self, content: bytes) -> Digest:
        digest = digest_of(content)
        response = await self._send("PUT", self._url(digest), content)
        if response.status_code != 200:
            raise ObjectStoreUnavailable(f"the object store refused the object: {_error(response)}")
        self._cache.keep(digest, content)
        return digest

    async def get(self, digest: Digest) -> bytes | None:
        cached = self._cache.get(digest)
        if cached is not None:
            return cached
        if not _DIGEST.fullmatch(digest):
            return None
        url = self._url(digest)
        response = await self._send("GET", url, b"")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ObjectStoreUnavailable(f"the object store refused the read: {_error(response)}")
        found = verified(digest, response.content, where=url)
        if found is not None:
            self._cache.keep(digest, found)
        return found
