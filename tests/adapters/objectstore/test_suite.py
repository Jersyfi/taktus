"""One suite for every adapter of the object store port (ADR-0165 §2, #342).

Each adapter is given a place and opened over it: memory alone, a directory (`filesystem`, the
default), and a bucket of an S3-compatible store. The store is `rclone serve s3` from the backup
image, an implementation of the interface and its signature that is not ours, on a random
port of this machine; without Docker those cases skip and say so, unless
`TAKTUS_REQUIRE_DATABASE` says nothing may skip (DEC-0004).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import images
import pytest
from conftest import built, docker_available

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.s3 import S3ObjectStore, sign
from taktus.ports.configuration import Secret
from taktus.ports.objectstore import ObjectStore, ObjectStoreUnavailable

BUCKET = "artifacts"
PREFIX = "instance/objects"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if check and done.returncode != 0:
        raise AssertionError(f"docker {args[:3]}… failed: {done.stdout}\n{done.stderr}")
    return done


@dataclass(frozen=True)
class Server:
    endpoint: str
    identifier: str
    key: str


@pytest.fixture(scope="module")
def s3_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    reason = docker_available()
    if reason is not None:
        message = f"the S3-compatible adapter's cases need Docker for their server: {reason}"
        if os.environ.get("TAKTUS_REQUIRE_DATABASE"):
            pytest.fail(message + " — and TAKTUS_REQUIRE_DATABASE says they may not skip")
        pytest.skip(message)
    backup_image = built(images.BACKUP)
    data = tmp_path_factory.mktemp("s3")
    (data / BUCKET).mkdir()
    identifier, key = "objectstore-test", os.urandom(16).hex()
    container = docker(
        "run", "--detach", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
        "--publish", "127.0.0.1::8333", f"--volume={data}:/data",
        "--entrypoint=rclone", backup_image,
        "serve", "s3", "--config", "/dev/null", "--addr", "0.0.0.0:8333",
        "--auth-key", f"{identifier},{key}", "/data",
    ).stdout.strip()  # fmt: skip
    try:
        port = (
            docker("port", container, "8333/tcp").stdout.strip().splitlines()[0].rsplit(":", 1)[1]
        )
        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                httpx.get(endpoint, timeout=2)
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        yield Server(endpoint, identifier, key)
    finally:
        docker("stop", container, check=False)


async def put_by_hand(server: Server, key: str, content: bytes) -> None:
    """One key written through the interface, as any client of it would, not through the
    adapter."""
    url = f"{server.endpoint}/{BUCKET}/{key}"
    headers = sign(
        method="PUT", url=url, payload_hash=hashlib.sha256(content).hexdigest(),
        access_key_id=server.identifier, secret_key=server.key,
        region="us-east-1", now=datetime.now(UTC),
    )  # fmt: skip
    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=content, headers=headers)
    assert response.status_code == 200, response.text


@dataclass
class Opened:
    """An adapter's way to open a store over its place, and to spoil one object in it."""

    open: Callable[[], ObjectStore]
    spoil: Callable[[str, bytes], Awaitable[None]] | None


async def _closed(store: ObjectStore) -> None:
    if isinstance(store, S3ObjectStore):
        await store.aclose()


@pytest.fixture(params=["memory", "filesystem", "s3"])
async def adapter(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Opened]:
    if request.param == "memory":
        one = MemoryObjectStore()
        yield Opened(lambda: one, None)
        return
    if request.param == "filesystem":
        directory = tmp_path / "objects"

        async def spoil_file(digest: str, content: bytes) -> None:
            (directory / digest.removeprefix("sha256:")).write_bytes(content)

        yield Opened(lambda: MemoryObjectStore(directory, cache_bytes=0), spoil_file)
        return
    server: Server = request.getfixturevalue("s3_server")
    prefix = f"{PREFIX}/{request.node.name.replace('[', '-').replace(']', '')}"
    opened: list[S3ObjectStore] = []

    def open_s3() -> ObjectStore:
        store = S3ObjectStore(
            endpoint=server.endpoint,
            bucket=BUCKET,
            prefix=prefix,
            access_key_id=Secret(server.identifier),
            secret_key=Secret(server.key),
            cache_bytes=0,
        )
        opened.append(store)
        return store

    async def spoil_key(digest: str, content: bytes) -> None:
        await put_by_hand(server, f"{prefix}/{digest.removeprefix('sha256:')}", content)

    yield Opened(open_s3, spoil_key)
    for store in opened:
        await store.aclose()


async def test_put_names_the_bytes_by_their_digest_and_get_returns_them(adapter: Opened) -> None:
    store = adapter.open()
    content = os.urandom(2048)
    digest = await store.put(content)
    assert digest == "sha256:" + hashlib.sha256(content).hexdigest()
    assert await store.get(digest) == content
    assert await store.put(b"") == "sha256:" + hashlib.sha256(b"").hexdigest()
    assert await store.get(await store.put(b"")) == b""


async def test_the_same_bytes_twice_are_one_object(adapter: Opened) -> None:
    store = adapter.open()
    first = await store.put(b"once")
    assert await store.put(b"once") == first
    assert await store.get(first) == b"once"


async def test_a_digest_never_written_reads_as_absent(adapter: Opened) -> None:
    store = adapter.open()
    assert await store.get("sha256:" + "0" * 64) is None
    assert await store.get("sha256:not-a-digest") is None


async def test_an_object_outlives_the_store_that_wrote_it(adapter: Opened) -> None:
    writer = adapter.open()
    digest = await writer.put(b"kept")
    await _closed(writer)
    assert await adapter.open().get(digest) == b"kept"


async def test_bytes_that_do_not_hash_to_their_name_read_as_absent(adapter: Opened) -> None:
    if adapter.spoil is None:
        pytest.skip("memory alone holds what it computed; nothing can change it under it")
    digest = await adapter.open().put(b"written")
    await adapter.spoil(digest, b"something else")
    assert await adapter.open().get(digest) is None


async def test_a_store_that_cannot_be_reached_raises_and_never_reads_as_absent(
    tmp_path: Path,
) -> None:
    secret = os.urandom(8).hex()
    unreachable = S3ObjectStore(
        endpoint="http://127.0.0.1:9",
        bucket=BUCKET,
        access_key_id=Secret("id"),
        secret_key=Secret(secret),
        timeout_seconds=2,
    )
    with pytest.raises(ObjectStoreUnavailable) as raised:
        await unreachable.get("sha256:" + "1" * 64)
    assert secret not in str(raised.value)
    with pytest.raises(ObjectStoreUnavailable):
        await unreachable.put(b"x")
    await unreachable.aclose()
    blocked = tmp_path / "a-file"
    blocked.write_bytes(b"")
    with pytest.raises(ObjectStoreUnavailable):
        await MemoryObjectStore(blocked / "objects").put(b"x")


async def test_a_credential_the_store_refuses_raises_and_is_never_named(
    s3_server: Server,
) -> None:
    wrong = os.urandom(16).hex()
    store = S3ObjectStore(
        endpoint=s3_server.endpoint,
        bucket=BUCKET,
        access_key_id=Secret(s3_server.identifier),
        secret_key=Secret(wrong),
    )
    with pytest.raises(ObjectStoreUnavailable) as raised:
        await store.put(b"refused")
    with pytest.raises(ObjectStoreUnavailable):
        await store.get("sha256:" + "2" * 64)
    await store.aclose()
    assert wrong not in str(raised.value) and s3_server.key not in str(raised.value)


async def test_the_keys_are_the_prefix_and_the_hex_the_filesystem_names_its_files(
    s3_server: Server, tmp_path: Path
) -> None:
    """ADR-0165 §5: moving an instance is a copy of `objects/` into the bucket under the
    prefix. A file the filesystem adapter wrote, copied there by a client of the interface,
    is read by the other."""
    filesystem = MemoryObjectStore(tmp_path / "objects")
    digest = await filesystem.put(b"moved by hand")
    for path in (tmp_path / "objects").iterdir():
        await put_by_hand(s3_server, f"moved/{path.name}", path.read_bytes())
    store = S3ObjectStore(
        endpoint=s3_server.endpoint,
        bucket=BUCKET,
        prefix="moved",
        access_key_id=Secret(s3_server.identifier),
        secret_key=Secret(s3_server.key),
    )
    assert await store.get(digest) == b"moved by hand"
    await store.aclose()
