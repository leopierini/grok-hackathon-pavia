"""Scripted configuration cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.connect",
    "dog.run_route",
    "dog.prepare",
    "drone.connect",
    "drone.inspect",
    "reasoner.assess_incident",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        *,
        teardown: tuple[str, ...] = _TEARDOWN,
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-02",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=_FORBIDDEN,
            teardown=teardown,
        )

    def ok(case_id: str, trace: tuple[str, ...], *, device_calls: int = 0) -> SimulationCase:
        return make(
            case_id,
            {
                "status": "ok",
                "trace": trace,
                "device_calls": device_calls,
                "live_call_count": 0,
                "simulated": True,
                "authorized": False,
                "slot": "base.config",
                "schema_version": SCHEMA_VERSION,
            },
        )

    def rejected(case_id: str, code: str, detail: str) -> SimulationCase:
        return make(
            case_id,
            {
                "status": "failed",
                "error_code": code,
                "error_detail": detail,
                "device_calls": 0,
                "live_call_count": 0,
            },
        )

    return (
        ok(
            "nested_absolute_paths",
            (
                "cwd_independent",
                "routes_from_dog_file",
                "output_root_absolute",
                "transport:ethernet",
                "sdk:DJITelloPy",
                "radio:wifi",
            ),
        ),
        ok(
            "transport_profiles",
            (
                "transport:ethernet",
                "transport:wifi",
                "physical_acceptance:not_accepted",
                "modes_unchanged",
                "vendor_mode_independent",
            ),
        ),
        rejected("malformed_json", "invalid_input", "malformed JSON rejected"),
        rejected("missing_real_keys", "invalid_input", "missing key rejected"),
        rejected("nonfinite_limits", "invalid_input", "numeric limit rejected"),
        rejected("path_resolution_failure", "io_fault", "path resolution rejected"),
        ok(
            "optional_flight_disabled",
            ("flight:disabled", "drone_mode:fake", "dog_mode:real", "fallback:none"),
        ),
        ok(
            "readiness_no_fallback",
            ("transport:ethernet", "fallback:none", "adapters.build", "dog_mode:real"),
            device_calls=1,
        ),
        ok("redacted_secrets", ("secrets_absent",)),
        ok("stable_key_order", ("order_stable",)),
        ok("source_not_rewritten", ("source_unchanged",)),
        rejected("duplicate_key", "invalid_input", "duplicate key rejected"),
        rejected("pad_fake_dog", "invalid_input", "pad combination rejected"),
    )
