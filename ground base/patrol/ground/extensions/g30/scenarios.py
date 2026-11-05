"""Scripted link cases. The harness runs the real provider against these expectations."""

from __future__ import annotations

from collections.abc import Callable

from patrol.ground.extensions.g30.implementation import SCHEMA, SLOT
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = (
    "dog.run_route",
    "drone.inspect",
    "reasoner.assess_incident",
    "execute",
    "takeoff",
    "move",
    "join_wifi",
    "change_route",
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
        trace: tuple[str, ...],
        detail: str,
        *,
        status: str = "ok",
        error_code: str | None = None,
    ) -> SimulationCase:
        expected: dict[str, object] = {
            "status": status,
            "authorized": False,
            "retained": False,
            "detail": detail,
            "trace": trace,
            "device_calls": 0,
            "live_call_count": 0,
            "simulated": True,
            "within_limit": True,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
        if error_code is not None:
            expected["error_code"] = error_code
            expected["error_detail"] = detail
        return SimulationCase(
            task_id="GROUND-30",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=_MOTION,
            teardown=_TEARDOWN,
        )

    ethernet = _view("ethernet-tether", "ethernet")
    wifi = _view("wifi-lan", "wifi", pi_path="second_radio")
    return (
        make("ethernet_ready", ethernet(), "ready:ethernet-tether"),
        make(
            "ethernet_no_tether",
            ethernet(tether="missing", ready="false"),
            "blocked:tether_acceptance",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "missing_pi_path",
            ethernet(
                pi_path="missing",
                telemetry="false",
                rssi="blocked",
                ready="false",
                extras=("dog_rssi_receiver:ignored", "heartbeat:ignored_without_path"),
            ),
            "blocked:pi_path",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "tello_without_pi",
            ethernet(
                pi_path="missing",
                telemetry="false",
                rssi="blocked",
                ready="false",
                extras=(
                    "dog_rssi_receiver:ignored",
                    "heartbeat:ignored_without_path",
                    "tello_ap:not_a_pi_path",
                ),
            ),
            "blocked:pi_path",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "transport_switch",
            ethernet(
                ready="false",
                extras=("dog_rssi_receiver:ignored", "handover:rejected", "switch:wifi"),
            ),
            "blocked:transport_switch",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "dog_link_drop",
            ethernet(
                dog="down",
                ready="false",
                extras=(
                    "dog_rssi_receiver:ignored",
                    "flap:dog",
                    "request_safety:true",
                    "latch:task28",
                ),
            ),
            "blocked:dog_link",
            status="blocked",
            error_code="unavailable",
        ),
        make("router_separate", ethernet(), "ready:ethernet-tether"),
        make(
            "route_change",
            ("action:change_route", "repair:rejected", "ready:false", "sockets:none"),
            "blocked:route_change",
            status="failed",
            error_code="forbidden_command",
        ),
        make(
            "secrets_redacted",
            ethernet(extras=("secrets:redacted", "dog_rssi_receiver:ignored")),
            "ready:ethernet-tether",
        ),
        make("wifi_ready", wifi(), "ready:wifi-lan"),
        make(
            "wifi_no_acceptance",
            wifi(wifi_acceptance="missing", ready="false"),
            "blocked:wifi_acceptance",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "no_fallback",
            ethernet(
                dog="down",
                ready="false",
                extras=("dog_rssi_receiver:ignored", "handover:rejected", "fallback:wifi"),
            ),
            "blocked:transport_switch",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "simulated_real_mode",
            ethernet(mode="real", telemetry="false", rssi="blocked", ready="false"),
            "blocked:simulated_probe",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "physical_claim",
            ("rejected", "physical_claim", "sockets:none"),
            "blocked:physical_claim",
            status="failed",
            error_code="invalid_input",
        ),
        make(
            "string_tether",
            ("rejected", "tether_accepted_type", "sockets:none"),
            "blocked:tether_accepted_type",
            status="failed",
            error_code="invalid_input",
        ),
        make(
            "pi_link_down",
            ethernet(pi="down", telemetry="false", rssi="blocked", ready="false"),
            "blocked:pi_link",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "internet_down",
            ethernet(internet="down", ready="false"),
            "blocked:internet_link",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "not_simultaneous",
            ("rejected", "not_simultaneous", "sockets:none"),
            "blocked:not_simultaneous",
            status="failed",
            error_code="invalid_input",
        ),
        make(
            "router_not_pi_excuse",
            ethernet(
                pi_path="missing",
                telemetry="false",
                rssi="blocked",
                ready="false",
                extras=("dog_rssi_receiver:ignored", "heartbeat:ignored_without_path"),
            ),
            "blocked:pi_path",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "unknown_pi_path",
            ("rejected", "unknown_pi_path", "sockets:none"),
            "blocked:unknown_pi_path",
            status="failed",
            error_code="invalid_input",
        ),
        make(
            "pi_data_path",
            ethernet(
                telemetry="false",
                rssi="blocked",
                ready="false",
                extras=("dog_rssi_receiver:ignored", "tello_ap:not_a_laptop_route"),
            ),
            "blocked:pi_data_path",
            status="blocked",
            error_code="rejected",
        ),
    )


def _view(
    profile: str, transport: str, *, pi_path: str = "usb"
) -> Callable[..., tuple[str, ...]]:
    tether = "accepted" if transport == "ethernet" else "not_required"
    wifi_acceptance = "not_required" if transport == "ethernet" else "accepted"

    def build(
        *,
        mode: str = "simulated",
        pi_path: str = pi_path,
        dog: str = "up",
        drone: str = "up",
        pi: str = "up",
        internet: str = "up",
        telemetry: str = "true",
        tether: str = tether,
        wifi_acceptance: str = wifi_acceptance,
        rssi: str = "armed",
        ready: str = "true",
        extras: tuple[str, ...] = ("dog_rssi_receiver:ignored",),
    ) -> tuple[str, ...]:
        return (
            f"profile:{profile}",
            f"transport:{transport}",
            f"mode:{mode}",
            f"pi_path:{pi_path}",
            f"dog:{dog}",
            f"drone:{drone}",
            f"pi:{pi}",
            f"internet:{internet}",
            "dog_identified:true",
            "drone_identified:true",
            f"pi_telemetry:{telemetry}",
            f"tether:{tether}",
            f"wifi_acceptance:{wifi_acceptance}",
            "router:back_enclosure_failed",
            "router_is_not_pi:true",
            f"rssi:{rssi}",
            f"ready:{ready}",
            "evidence:simulated",
            "sockets:none",
            *extras,
        )

    return build
