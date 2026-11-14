"""The model port over Vertex AI's `generateContent`, against a stand-in of the service and of its
token endpoint built from the published interface (`adapters/driven/models/README.md`;
UC-8.1, ADR-0248): a service account's key becomes an access token by a signed assertion, the
prompt goes out as `contents` with its system text and limit, the answer comes back with its
usage by price kind, a European regional endpoint processes in `eu`, and no key reaches an
error."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import vertex_service

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.models.vertex import VertexModel, location_of
from taktus.composition.execution import model_pool
from taktus.composition.settings import load_models
from taktus.ports.configuration import Secret
from taktus.ports.model import ModelAtLimit, ModelError, Prompt

REGION = "europe-west1"


@pytest.fixture
def service() -> Iterator[tuple[str, Secret, vertex_service.Script]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server, script = vertex_service.make_server(private.public_key())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    key = {
        "type": "service_account",
        "client_email": "taktus@project.iam.gserviceaccount.com",
        "private_key_id": "k1",
        "private_key": pem,
        "token_uri": script.token_uri,
    }
    base = script.token_uri.removesuffix("/token")
    endpoint = f"{base}/v1/projects/acme/locations/{REGION}/publishers/google/models"
    try:
        yield endpoint, Secret(json.dumps(key)), script
    finally:
        server.shutdown()
        server.server_close()


async def test_a_prompt_goes_out_as_contents_and_comes_back_with_its_usage(
    service: tuple[str, Secret, vertex_service.Script],
) -> None:
    endpoint, key, script = service
    script.cached, script.thoughts = 3, 2
    model = VertexModel(endpoint, "gemini-x", credential=key, timeout=5.0)
    completion = await model.complete(
        Prompt(system="Antworte knapp.", user="Danke für die Lieferung", max_output_tokens=64)
    )
    assert completion.text == "Gern geschehen." and completion.finish == "stop"
    assert completion.model == "gemini-x-001"
    assert completion.tokens_in == 4 + 3 and completion.tokens_out == 2 + 2
    assert completion.by_kind is not None
    assert (completion.by_kind.input, completion.by_kind.cache_read) == (4, 3)
    (request,) = script.requests
    assert request["contents"] == [{"role": "user", "parts": [{"text": "Danke für die Lieferung"}]}]
    assert request["systemInstruction"] == {"parts": [{"text": "Antworte knapp."}]}
    assert request["generationConfig"] == {"maxOutputTokens": 64}
    assert script.paths[0].endswith(
        f"/locations/{REGION}/publishers/google/models/gemini-x:generateContent"
    )
    await model.complete(Prompt(user="noch einmal", max_output_tokens=8))
    assert len(script.tokens) == 1, "the access token is kept until it nearly expires"


async def test_the_output_limit_ends_the_answer_as_cut(
    service: tuple[str, Secret, vertex_service.Script],
) -> None:
    endpoint, key, script = service
    script.answer = "eins zwei drei vier fünf"
    completion = await VertexModel(endpoint, "gemini-x", credential=key).complete(
        Prompt(user="zähle", max_output_tokens=2)
    )
    assert completion.finish == "length" and completion.text == "eins zwei"


async def test_a_refusal_names_the_endpoint_and_never_the_key(
    service: tuple[str, Secret, vertex_service.Script],
) -> None:
    endpoint, key, script = service
    script.status = 429
    with pytest.raises(ModelAtLimit):
        await VertexModel(endpoint, "gemini-x", credential=key).complete(Prompt(user="x"))
    script.status = 500
    with pytest.raises(ModelError) as failed:
        await VertexModel(endpoint, "gemini-x", credential=key).complete(Prompt(user="x"))
    assert endpoint in str(failed.value) and "PRIVATE KEY" not in str(failed.value)
    with pytest.raises(ModelError) as unusable:
        await VertexModel(endpoint, "gemini-x", credential=Secret("not json")).complete(
            Prompt(user="x")
        )
    assert "service account's key file" in str(unusable.value)


def test_a_regional_endpoint_names_where_it_processes() -> None:
    eu = "https://europe-west4-aiplatform.googleapis.com/v1/projects/p/locations/europe-west4"
    us = "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1"
    world = "https://aiplatform.googleapis.com/v1/projects/p/locations/global"
    assert [location_of(e) for e in (eu, us, world)] == ["eu", "elsewhere", "elsewhere"]


async def test_configured_by_its_dialect_it_is_an_eu_member_a_residency_rule_admits() -> None:
    endpoint = (
        "https://europe-west1-aiplatform.googleapis.com/v1/projects/acme/locations/"
        "europe-west1/publishers/google/models"
    )
    pool = model_pool(
        load_models(
            EnvironmentConfiguration(
                {
                    "TAKTUS_MODEL_DIALECT": "generate_content",
                    "TAKTUS_MODEL_ENDPOINT": endpoint,
                    "TAKTUS_MODEL_NAME": "gemini-x",
                }
            )
        )
    )
    (member,) = await pool.chain("drafting")
    assert isinstance(member.model, VertexModel) and member.location == "eu"
