"""Enqueue, flush, publish, and replay. A failed flush is not a saved log."""

from __future__ import annotations

from patrol.ground.extensions.g29.implementation import LogFeature
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.faults import fault
from tests.ground.g29.conftest import journal_count, load_example, request, run


def test_enqueue_is_not_published(feature: LogFeature, services: BaseServices) -> None:
    async def body() -> None:
        result = await feature.execute(
            request("accept", {"envelope": load_example("pi-heartbeat.json")})
        )
        assert result.status == "ok"
        assert result.data["published"] is False
        assert result.data["writer_state"] == "queued"
        assert getattr(services.journal, "published", None) is None
        record = feature.records[0]
        assert record["published"] is False

    run(body)


def test_publish_before_flush_is_refused(feature: LogFeature, services: BaseServices) -> None:
    async def body() -> None:
        await feature.execute(request("accept", {"envelope": load_example("pi-heartbeat.json")}))
        result = await feature.execute(request("publish", {}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["published"] is False
        assert getattr(services.journal, "published", None) is None
        assert feature.records[0]["writer_state"] == "queued"

    run(body)


def test_flush_then_publish_marks_durability(feature: LogFeature, services: BaseServices) -> None:
    async def body() -> None:
        await feature.execute(request("accept", {"envelope": load_example("pi-heartbeat.json")}))
        flushed = await feature.execute(request("flush", {}))
        assert flushed.status == "ok"
        assert flushed.data["published"] is False
        assert flushed.data["writer_state"] == "flushed"
        assert feature.records[0]["writer_state"] == "flushed"
        assert getattr(services.journal, "published", None) is None
        published = await feature.execute(request("publish", {}))
        assert published.status == "ok"
        assert published.data["published"] is True
        assert feature.records[0]["published"] is True
        summary = getattr(services.journal, "published", None)
        assert isinstance(summary, dict)
        assert summary["published"] is True
        assert summary["logs_requirements_status"] == "proposed_pending_team"

    run(body)


def test_failed_flush_does_not_publish(feature: LogFeature, services: BaseServices) -> None:
    async def body() -> None:
        await feature.execute(request("accept", {"envelope": load_example("pi-heartbeat.json")}))

        async def boom() -> None:
            raise fault("io_fault", "journal flush failed", recovery_required=True)

        services.journal.flush = boom
        result = await feature.execute(request("flush", {}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "io_fault"
        assert result.data["published"] is False
        assert result.data["writer_state"] == "failed"
        assert result.events[0].kind == "persistence_fault"
        assert result.events[0].payload["published"] is False
        assert feature.records[0]["writer_state"] == "failed"
        assert feature.records[0]["published"] is False
        assert feature.faults[0]["category"] == "persistence"
        assert getattr(services.journal, "published", None) is None
        refused = await feature.execute(request("publish", {}))
        assert refused.status == "failed"
        assert refused.data["published"] is False
        assert getattr(services.journal, "published", None) is None

    run(body)


def test_same_message_id_does_not_append(feature: LogFeature, services: BaseServices) -> None:
    async def body() -> None:
        envelope = load_example("pi-heartbeat.json")
        first = await feature.execute(request("accept", {"envelope": envelope}))
        second = await feature.execute(request("accept", {"envelope": envelope}))
        assert first.status == "ok"
        assert second.status == "ok"
        assert second.data["duplicate"] is True
        assert first.data["message_id"] == second.data["message_id"]
        assert len(feature.records) == 1
        assert journal_count(services) == 1
        assert feature.records[0]["sequence"] == 1

    run(body)
