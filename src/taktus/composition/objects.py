"""The object store the daemon holds artifact bytes in, chosen by `TAKTUS_OBJECT_STORE`
(ADR-0165 §1): the directory under the state directory, or a bucket of an S3-compatible
store."""

from __future__ import annotations

from pathlib import Path

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.s3 import S3ObjectStore
from taktus.composition.settings import ObjectStoreSettings
from taktus.ports.objectstore import ObjectStore


def object_store_of(
    settings: ObjectStoreSettings, *, state_dir: Path, cache_bytes: int
) -> ObjectStore:
    if settings.kind == "s3":
        # load_object_store refuses `s3` without any of these.
        if not (settings.endpoint and settings.bucket):
            raise ValueError("the object store s3 needs its endpoint and bucket")
        if settings.access_key_id is None or settings.secret_key is None:
            raise ValueError("the object store s3 needs its credential")
        return S3ObjectStore(
            endpoint=settings.endpoint,
            bucket=settings.bucket,
            prefix=settings.prefix,
            region=settings.region,
            access_key_id=settings.access_key_id,
            secret_key=settings.secret_key,
            cache_bytes=cache_bytes,
        )
    return MemoryObjectStore(state_dir / "objects", cache_bytes=cache_bytes)
