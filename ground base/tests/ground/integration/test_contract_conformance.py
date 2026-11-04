"""Check every published wire example and systematically corrupt required fields."""

from __future__ import annotations

import asyncio
import copy
import json
import random
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from patrol.ground.extensions.g11.implementation import create
from patrol.ground.extensions.g11.schema_check import SchemaFault, validate_message
from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services

ROOT = repo_root() / "contracts"
SCHEMA: dict[str, Any] = json.loads((ROOT / "message.schema.json").read_text())
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))


def example(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def test_schema_copy_is_exact_and_standard_schema_is_valid() -> None:
    frozen = repo_root() / "fixtures/ground/g11/message.schema.json"
    assert json.loads(frozen.read_text()) == SCHEMA
    Draft202012Validator.check_schema(SCHEMA)
    assert len(EXAMPLES) == 32


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_published_example_is_accepted_by_both_validators(path: Path) -> None:
    document = example(path)
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(document)
    validate_message(document, SCHEMA)
    assert document["simulated"] is True


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
@pytest.mark.parametrize("key", SCHEMA["required"])
def test_every_required_envelope_field_is_enforced(path: Path, key: str) -> None:
    document = example(path)
    del document[key]
    assert not Draft202012Validator(SCHEMA).is_valid(document)
    with pytest.raises(SchemaFault):
        validate_message(document, SCHEMA)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_every_required_payload_field_and_unknown_field_is_enforced(path: Path) -> None:
    document = example(path)
    fields = SCHEMA["$defs"][document["kind"]]["required"]
    for field in fields:
        mutated = copy.deepcopy(document)
        del mutated["payload"][field]
        assert not Draft202012Validator(SCHEMA).is_valid(mutated), field
        with pytest.raises(SchemaFault):
            validate_message(mutated, SCHEMA)
    document["payload"]["unapproved_extension"] = "takeoff"
    with pytest.raises(SchemaFault):
        validate_message(document, SCHEMA)


@pytest.mark.parametrize("seed", [0, 7, 29])
def test_seeded_malformed_envelopes_never_reach_a_device(tmp_path: Path, seed: int) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("contract fuzz")
        gate = create(services)
        rng = random.Random(seed)
        for index in range(100):
            document = example(rng.choice(EXAMPLES))
            document["message_id"] = f"fuzz-{seed}-{index}"
            key = rng.choice(("epoch", "seq", "simulated", "protocol_version", "payload"))
            document[key] = {
                "epoch": True,
                "seq": -1,
                "simulated": "true",
                "protocol_version": "1.0",
                "payload": [],
            }[key]
            result = await gate.execute(
                FeatureRequest(
                    "guard",
                    "v2_envelope",
                    None,
                    {
                        "message": json.dumps(document),
                        "epoch": 1,
                        "expected_source": document["source"],
                        "expected_destination": document["destination"],
                    },
                )
            )
            assert result.status == "blocked"
        assert services.adapters.devices.calls == []

    asyncio.run(run())
