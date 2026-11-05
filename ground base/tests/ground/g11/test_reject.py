"""Malformed envelopes and expired ordinary commands are blocked before motion."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g11.schema_check import fixture_root
from tests.ground.g11.support import calls, load, request_for, run, services
from tests.ground.g11.test_accept import create_port


def test_parse_failures_have_stable_diagnostics(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        samples = {
            "truncated.json": "invalid_json",
            "comment.json": "invalid_json",
            "trailing-comma.json": "invalid_json",
            "second-value.json": "trailing_json",
        }
        for name, diagnostic in samples.items():
            raw = (fixture_root() / name).read_text(encoding="utf-8")
            result = await run(port, request_for(load("drone-observation.json"), raw=raw))
            assert result.status == "blocked"
            assert result.error is not None
            assert result.error.detail == diagnostic
        bom_bytes = (fixture_root() / "bom.json").read_bytes()
        bom = await run(port, request_for(load("drone-observation.json"), raw=bom_bytes))
        assert bom.error is not None
        assert bom.error.detail == "utf8_bom"
        duplicate = '{"protocol_version":"2.0-draft","protocol_version":"2.0-draft"}'
        repeated = await run(port, request_for(load("drone-observation.json"), raw=duplicate))
        assert repeated.error is not None
        assert repeated.error.detail == "invalid_json"
        assert calls(built) == []

    asyncio.run(body())


def test_schema_direction_epoch_and_synthetic_hash(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        unknown = load("drone-observation.json")
        unknown["kind"] = "teleport"
        extra = load("drone-observation.json")
        extra["note"] = "nope"
        payload_extra = load("drone-observation.json")
        body_payload = payload_extra["payload"]
        assert isinstance(body_payload, dict)
        body_payload["note"] = "nope"
        synthetic = load("drone-observation.json")
        synthetic["simulated"] = False
        wrong = load("ground-to-drone-command.json")
        wrong["source"] = "vision"
        epoch = load("drone-observation.json")
        epoch["message_id"] = "msg-bad-epoch"
        epoch["epoch"] = 9
        string_bool = load("drone-observation.json")
        string_bool["message_id"] = "msg-string-bool"
        string_bool["simulated"] = "true"
        operator = load("drone-observation.json")
        operator["message_id"] = "msg-operator"
        operator["source"] = "operator"
        cases = {
            "unknown_kind": unknown,
            "unknown_field": extra,
            "payload_shape": payload_extra,
            "simulated_synthetic": synthetic,
            "direction": wrong,
            "epoch_mismatch": epoch,
        }
        for diagnostic, message in cases.items():
            result = await run(port, request_for(message))
            assert result.status == "blocked", diagnostic
            assert result.error is not None
            assert result.error.detail == diagnostic
        typed = await run(port, request_for(string_bool))
        assert typed.error is not None
        assert typed.error.detail == "invalid_type"
        foreign = await run(port, request_for(operator))
        assert foreign.error is not None
        assert foreign.error.detail == "direction"
        assert calls(built) == []

    asyncio.run(body())


def test_null_expiry_and_ordinary_expiry_do_not_block_halt(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        request = load("drone-vision-request.json")
        request["expires_at"] = None
        proposal = load("ai-to-drone-proposal.json")
        proposal["message_id"] = "msg-proposal-null-expiry"
        proposal["expires_at"] = None
        expired = load("ground-to-drone-command.json")
        expired["expires_at"] = "2025-12-31T00:00:00Z"
        hover = load("ground-to-drone-hover.json")
        hover["expires_at"] = "2025-12-31T00:00:00Z"
        land = load("ground-to-drone-land.json")
        land["expires_at"] = "2025-12-31T00:00:00Z"
        halt = load("ground-to-dog-halt.json")
        halt["expires_at"] = "2025-12-31T00:00:00Z"
        missing = await run(port, request_for(request))
        proposal_result = await run(port, request_for(proposal))
        motion = await run(port, request_for(expired))
        hover_result = await run(port, request_for(hover))
        land_result = await run(port, request_for(land))
        halt_result = await run(port, request_for(halt))
        assert missing.error is not None and missing.error.detail == "expiry_required"
        assert proposal_result.error is not None
        assert proposal_result.error.detail == "expiry_required"
        assert motion.error is not None and motion.error.detail == "expired"
        assert hover_result.error is not None and hover_result.error.detail == "expired"
        assert land_result.status == "ok" and land_result.data["safety_command"] is True
        assert halt_result.status == "ok" and halt_result.data["safety_command"] is True
        assert calls(built) == []

    asyncio.run(body())


def test_expected_peer_must_match_the_envelope(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        result = await run(
            create_port(built),
            request_for(load("drone-observation.json"), expected_source="dog"),
        )
        assert result.error is not None
        assert result.error.detail == "direction"
        assert calls(built) == []

    asyncio.run(body())
