"""Secrets, image bytes, and unknown measurements stay out of the journal line."""

from __future__ import annotations

import json

from patrol.ground.extensions.g29.implementation import LogFeature
from tests.ground.g29.conftest import load_example, request, run


def _line(record: object) -> str:
    return json.dumps(record, sort_keys=True)


def test_api_key_is_removed_and_named(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("ground-to-dog-command.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        payload["api_key"] = "sk-test-value-not-for-journal"
        payload["authorization"] = "Bearer should-not-leak"
        envelope["message_id"] = "msg-secret"
        result = await feature.execute(
            request(
                "accept",
                {
                    "envelope": envelope,
                    "secret_fields": ["api_key", "token", "authorization"],
                },
            )
        )
        assert result.status == "ok"
        record = result.data["record"]
        assert isinstance(record, dict)
        line = _line(record)
        assert "sk-test-value-not-for-journal" not in line
        assert "Bearer should-not-leak" not in line
        summary = record["summary"]
        assert isinstance(summary, dict)
        assert "api_key" not in summary
        assert "authorization" not in summary
        redacted = record["redacted_fields"]
        assert isinstance(redacted, list)
        assert "api_key" in redacted
        assert "authorization" in redacted
        assert record["command_id"] == "cmd-dog-001"

    run(body)


def test_injected_name_is_removed_without_a_hardcoded_value(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("pi-heartbeat.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        payload["session_cookie"] = "person-identifier"
        envelope["message_id"] = "msg-cookie"
        hidden = await feature.execute(
            request(
                "accept",
                {"envelope": envelope, "secret_fields": ["session_cookie"]},
            )
        )
        record = hidden.data["record"]
        assert isinstance(record, dict)
        assert "person-identifier" not in _line(record)
        kept = load_example("pi-heartbeat.json")
        kept_payload = kept["payload"]
        assert isinstance(kept_payload, dict)
        kept_payload["session_cookie"] = "person-identifier"
        kept["message_id"] = "msg-cookie-kept"
        shown = await feature.execute(request("accept", {"envelope": kept}))
        shown_record = shown.data["record"]
        assert isinstance(shown_record, dict)
        summary = shown_record["summary"]
        assert isinstance(summary, dict)
        assert summary["session_cookie"] == "person-identifier"

    run(body)


def test_image_bytes_are_dropped_and_hash_kept(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("drone-vision-request.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        frame = payload["frame"]
        assert isinstance(frame, dict)
        frame["image_bytes"] = "RAW-IMAGE-BYTES-NOT-FOR-JOURNAL"
        envelope["message_id"] = "msg-image"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        record = result.data["record"]
        assert isinstance(record, dict)
        assert "RAW-IMAGE-BYTES-NOT-FOR-JOURNAL" not in _line(record)
        assert record["artifact_sha256"] == frame["sha256"]
        assert record["artifact_ref"] == frame["image_ref"]
        omitted = record["omitted_fields"]
        assert isinstance(omitted, list)
        assert "frame.image_bytes" in omitted

    run(body)


def test_null_rssi_median_stays_null(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("pi-rssi-window.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        payload["median_rssi_dbm"] = None
        payload["height_estimate_m"] = "unknown"
        payload["battery_percent"] = True
        envelope["message_id"] = "msg-null-rssi"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        record = result.data["record"]
        assert isinstance(record, dict)
        summary = record["summary"]
        reasons = record["measurement_reasons"]
        assert isinstance(summary, dict)
        assert isinstance(reasons, dict)
        assert summary["median_rssi_dbm"] is None
        assert summary["median_rssi_dbm"] != 0
        assert reasons["median_rssi_dbm"] == "unknown"
        assert summary["height_estimate_m"] is None
        assert reasons["height_estimate_m"] == "unknown"
        assert summary["battery_percent"] is None
        assert reasons["battery_percent"] == "not_a_number"
        assert summary["spread_db"] == 4

    run(body)


def test_non_finite_measurement_is_not_zero(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("pi-rssi-window.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        payload["median_rssi_dbm"] = float("nan")
        envelope["message_id"] = "msg-nan-rssi"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        record = result.data["record"]
        assert isinstance(record, dict)
        summary = record["summary"]
        reasons = record["measurement_reasons"]
        assert isinstance(summary, dict)
        assert isinstance(reasons, dict)
        assert summary["median_rssi_dbm"] is None
        assert reasons["median_rssi_dbm"] == "not_finite"

    run(body)
