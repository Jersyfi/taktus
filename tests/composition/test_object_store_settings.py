"""`TAKTUS_OBJECT_STORE` chooses the object store's adapter (ADR-0165 §1): the directory by
default, a bucket of an S3-compatible store with its endpoint, bucket and credential files, and
a start refused without one of them. The credential is never in the startup log."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.s3 import S3ObjectStore
from taktus.composition.objects import object_store_of
from taktus.composition.settings import load_object_store
from taktus.ports.configuration import ConfigurationError


def test_the_directory_is_the_default(tmp_path: Path) -> None:
    settings = load_object_store(EnvironmentConfiguration({}))
    assert settings.kind == "filesystem"
    assert settings.effective() == [("TAKTUS_OBJECT_STORE", "filesystem")]
    store = object_store_of(settings, state_dir=tmp_path, cache_bytes=0)
    assert isinstance(store, MemoryObjectStore)


def test_the_s3_store_reads_its_credential_from_files_and_never_shows_it(tmp_path: Path) -> None:
    identifier, key = os.urandom(6).hex(), os.urandom(16).hex()
    (tmp_path / "id").write_text(identifier, encoding="utf-8")
    (tmp_path / "key").write_text(key, encoding="utf-8")
    settings = load_object_store(
        EnvironmentConfiguration(
            {
                "TAKTUS_OBJECT_STORE": "s3",
                "TAKTUS_OBJECT_STORE_ENDPOINT": "https://store.example",
                "TAKTUS_OBJECT_STORE_BUCKET": "artifacts",
                "TAKTUS_OBJECT_STORE_PREFIX": "/instance/",
                "TAKTUS_OBJECT_STORE_ACCESS_KEY_ID_FILE": str(tmp_path / "id"),
                "TAKTUS_OBJECT_STORE_SECRET_KEY_FILE": str(tmp_path / "key"),
            }
        )
    )
    assert (settings.prefix, settings.region) == ("instance", "us-east-1")
    shown = repr(settings.effective())
    assert identifier not in shown and key not in shown
    assert f"file {tmp_path / 'key'}" in shown
    store = object_store_of(settings, state_dir=tmp_path, cache_bytes=0)
    assert isinstance(store, S3ObjectStore)


@pytest.mark.parametrize(
    ("missing", "named"),
    [
        ("TAKTUS_OBJECT_STORE_ENDPOINT", "TAKTUS_OBJECT_STORE_ENDPOINT"),
        ("TAKTUS_OBJECT_STORE_BUCKET", "TAKTUS_OBJECT_STORE_BUCKET"),
        ("TAKTUS_OBJECT_STORE_SECRET_KEY_FILE", "TAKTUS_OBJECT_STORE_SECRET_KEY_FILE"),
    ],
)
def test_the_s3_store_without_what_it_needs_refuses_the_start(
    tmp_path: Path, missing: str, named: str
) -> None:
    (tmp_path / "secret").write_text("x", encoding="utf-8")
    environment = {
        "TAKTUS_OBJECT_STORE": "s3",
        "TAKTUS_OBJECT_STORE_ENDPOINT": "https://store.example",
        "TAKTUS_OBJECT_STORE_BUCKET": "artifacts",
        "TAKTUS_OBJECT_STORE_ACCESS_KEY_ID_FILE": str(tmp_path / "secret"),
        "TAKTUS_OBJECT_STORE_SECRET_KEY_FILE": str(tmp_path / "secret"),
    }
    del environment[missing]
    with pytest.raises(ConfigurationError) as raised:
        load_object_store(EnvironmentConfiguration(environment))
    assert raised.value.setting == named


def test_an_unknown_store_refuses_the_start() -> None:
    with pytest.raises(ConfigurationError):
        load_object_store(EnvironmentConfiguration({"TAKTUS_OBJECT_STORE": "tape"}))
