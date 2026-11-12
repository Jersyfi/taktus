"""A model server on one's own hardware and Mistral's API, both over the chat-completions
dialect, against stand-ins of their published interfaces (ADR-0248, UC-8.1, UC-8.3;
`adapters/driven/models/README.md`), and the one-machine installation's local-first settings."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from fakes import model_service

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.models import OpenAiCompatibleModel
from taktus.composition.execution import model_pool
from taktus.composition.settings import LOCAL_ENDPOINT, load_models
from taktus.conformance import ModelSuiteOptions, Status, run_model_suite
from taktus.ports.configuration import ConfigurationError
from taktus.ports.model import ModelError, Prompt


@pytest.fixture
def endpoint() -> Iterator[tuple[str, model_service.Script]]:
    server, script = model_service.make_server("127.0.0.1", 0, answer="ok {prompt}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", script
    finally:
        server.shutdown()
        server.server_close()


async def test_a_server_serving_one_model_is_asked_for_it(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    script.models = ("llama-local",)
    model = OpenAiCompatibleModel(url, "")
    await model.complete(Prompt(user="hi"))
    assert script.requests[0]["model"] == "llama-local" and model.model_name == "llama-local"


async def test_a_server_serving_several_models_names_them_and_asks_for_a_name(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    script.models = ("a", "b")
    with pytest.raises(ModelError) as failed:
        await OpenAiCompatibleModel(url, "").complete(Prompt(user="hi"))
    assert "2 models (a, b)" in str(failed.value) and "TAKTUS_MODEL_NAME" in str(failed.value)
    assert script.requests == []


async def test_an_answer_cut_at_the_models_length_is_cut(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    script.finish = "model_length"
    completion = await OpenAiCompatibleModel(url, "mistral-small-latest").complete(
        Prompt(user="hi")
    )
    assert completion.finish == "length"


async def test_the_model_suite_passes_against_the_stand_in_of_mistrals_shape(
    endpoint: tuple[str, model_service.Script],
) -> None:
    """Mistral's API answers the dialect's shape (its OpenAPI specification): the suite holds
    the stand-in of it to the contract, as it would hold the live endpoint."""
    url, _ = endpoint
    report = await run_model_suite(
        ModelSuiteOptions(
            endpoint=url,
            model="mistral-small-latest",
            declaration={
                "contract": "model/v1",
                "input_count": "upper_bound",
                "output_cap": "soft",
                "usage_kinds": ["input", "output"],
                "billing": "per_token",
            },
        )
    )
    assert {c.status for c in report.checks} == {Status.PASSED}


async def test_mistral_configured_as_eu_is_a_member_an_eu_rule_admits() -> None:
    pool = model_pool(
        load_models(
            EnvironmentConfiguration(
                {
                    "TAKTUS_MODEL_ENDPOINT": "https://api.mistral.ai/v1",
                    "TAKTUS_MODEL_NAME": "mistral-small-latest",
                    "TAKTUS_MODEL_LOCATION": "eu",
                }
            )
        )
    )
    (member,) = await pool.chain("drafting")
    assert member.location == "eu"


def test_local_first_binds_every_purpose_to_the_local_server_as_own() -> None:
    (model,) = load_models(EnvironmentConfiguration({"TAKTUS_MODEL_LOCAL_FIRST": "true"}))
    assert (model.endpoint, model.location, model.billing, model.purposes, model.name) == (
        LOCAL_ENDPOINT,
        "own",
        "per_hardware_time",
        ("*",),
        "",
    )


def test_under_local_first_an_outside_model_declares_where_it_processes() -> None:
    environment = {
        "TAKTUS_MODEL_LOCAL_FIRST": "true",
        "TAKTUS_MODEL_ENDPOINT": "https://api.example.com/v1",
        "TAKTUS_MODEL_NAME": "m",
    }
    with pytest.raises(ConfigurationError) as refused:
        load_models(EnvironmentConfiguration(environment))
    assert refused.value.setting == "TAKTUS_MODEL_LOCATION"
    (model,) = load_models(
        EnvironmentConfiguration({**environment, "TAKTUS_MODEL_LOCATION": "elsewhere"})
    )
    assert model.location == "elsewhere"


def test_without_local_first_nothing_is_bound() -> None:
    assert load_models(EnvironmentConfiguration({})) == ()
