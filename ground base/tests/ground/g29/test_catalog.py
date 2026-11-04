"""The example catalog is a set of separate records, not one mission replay."""

from __future__ import annotations

from patrol.ground.extensions.g29.implementation import LogFeature
from tests.ground.g29.conftest import load_catalog, load_example, request, run


def test_catalog_stores_each_line(feature: LogFeature) -> None:
    async def body() -> None:
        lines = load_catalog()
        result = await feature.execute(request("catalog", {"lines": lines}))
        assert result.status == "ok"
        assert result.error is None
        assert result.data["accepted"] == len(lines)
        assert result.data["duplicates"] == 0
        assert result.data["rejected"] == 0
        assert result.data["published"] is False
        assert len(feature.records) == len(lines)
        names = {record["event_name"] for record in feature.records}
        assert "demo_goal_reached" in names
        assert "landing_unverified" in names
        ids = [record["message_id"] for record in feature.records]
        assert len(ids) == len(set(ids))

    run(body)


def test_catalog_keeps_earlier_line_when_a_later_line_is_rejected(feature: LogFeature) -> None:
    async def body() -> None:
        good = load_example("pi-heartbeat.json")
        bad = load_example("ground-to-dog-command.json")
        payload = bad["payload"]
        assert isinstance(payload, dict)
        del payload["command_id"]
        bad["message_id"] = "msg-catalog-bad"
        result = await feature.execute(request("catalog", {"lines": [good, bad]}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["accepted"] == 1
        assert result.data["rejected"] == 1
        assert len(feature.records) == 1
        assert feature.records[0]["message_id"] == good["message_id"]

    run(body)
