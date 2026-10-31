"""The object store in an S3-compatible store: the optional adapter of ADR-0002 (ADR-0165)."""

from taktus.adapters.driven.s3.object_store import S3ObjectStore, sign

__all__ = ["S3ObjectStore", "sign"]
