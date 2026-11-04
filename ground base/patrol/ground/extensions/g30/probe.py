"""Read-only link probe. This module does not open sockets or change routes."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.paths import repo_root

PI_PATHS = frozenset({"wired", "usb", "second_radio"})
TRANSPORTS = frozenset({"ethernet", "wifi"})
MODES = frozenset({"simulated", "real"})
EVIDENCE = frozenset({"simulated", "documented", "physically_demonstrated"})
LINKS = ("dog", "drone", "pi", "internet")
ALLOWED_ACTIONS = frozenset({"read_probe", "read_link", "read_route"})
FORBIDDEN_ACTIONS = frozenset(
    {
        "change_route",
        "add_route",
        "delete_route",
        "route_add",
        "firewall_change",
        "disable_firewall",
        "install_service",
        "repair_router",
        "join_wifi",
        "leave_wifi",
        "handover",
    }
)
SENSITIVE_KEYS = frozenset(
    {"password", "aes_key", "aes", "token", "secret", "api_key", "sensitive_values"}
)
ALLOWED_KEYS = frozenset(
    {
        "profile_name",
        "dog_transport",
        "probe_mode",
        "evidence",
        "pi_path",
        "tether_accepted",
        "wifi_accepted",
        "router_failed",
        "switch_to",
        "fallback_transport",
        "actions",
        "flapped",
        "links",
        "messages",
        "sequential",
        *SENSITIVE_KEYS,
    }
)
@dataclass(frozen=True)
class LinkReport:
    status: str
    detail: str
    error_code: str | None
    recovery_required: bool
    trace: tuple[str, ...]
    event_kind: str
    ready: bool
    profile_name: str
    dog_transport: str
    pi_path: str | None
    rssi_blocked: bool
    missing_path: str | None
    dog_identified: bool
    drone_identified: bool
    pi_telemetry: bool
    router_note: str
    request_safety: bool
    evidence: str
    simulated: bool


def scripted_probe(case_id: str) -> dict[str, object]:
    """Build one injected probe. The name selects a fixture mutation."""
    builder = _CASES.get(case_id)
    if builder is None:
        raise fault("invalid_input", f"unknown link case {case_id}")
    return builder()


def evaluate(probe: Mapping[str, object]) -> LinkReport:
    """Decide readiness from one injected snapshot. The probe is not mutated."""
    if not isinstance(probe, Mapping):
        return _early("blocked:probe_type")
    unknown = sorted(key for key in probe if key not in ALLOWED_KEYS)
    if unknown:
        return _early("blocked:unknown_field")
    sequential = probe.get("sequential", False)
    if not isinstance(sequential, bool):
        return _early("blocked:sequential_type")
    if sequential:
        return _early("blocked:not_simultaneous")
    try:
        profile = _profile(probe.get("profile_name"))
        transport = _choice(probe.get("dog_transport"), TRANSPORTS, "dog_transport")
        mode = _choice(probe.get("probe_mode"), MODES, "probe_mode")
        evidence = _choice(probe.get("evidence"), EVIDENCE, "evidence")
        pi_path = _pi_path(probe.get("pi_path", None))
        router_failed = _flag(probe.get("router_failed"), "router_flag")
        tether_accepted = _optional_flag(probe, "tether_accepted")
        wifi_accepted = _optional_flag(probe, "wifi_accepted")
        switch_to = _optional_transport(probe, "switch_to")
        fallback = _optional_transport(probe, "fallback_transport")
        actions = _actions(probe.get("actions"))
        flapped = _flapped(probe.get("flapped", ()))
        links = _links(probe.get("links"))
    except _BadProbe as exc:
        return _early(exc.detail)
    forbidden = next((name for name in actions if name in FORBIDDEN_ACTIONS), None)
    if forbidden is not None:
        return _forbidden(forbidden)
    if evidence == "physically_demonstrated" and (
        mode != "real" or any(item.simulated for item in links.values())
    ):
        return _early("blocked:physical_claim")
    messages = _messages(probe.get("messages", {}))
    dog_identified = _peer(messages.get("dog"), "dog", "capabilities.report")
    drone_identified = _peer(messages.get("drone"), "drone", "capabilities.report")
    heartbeat = _peer(messages.get("pi"), "pi", "heartbeat")
    pi = links["pi"]
    path_known = pi_path in PI_PATHS
    tello_only = pi.joined_tello_ap_only
    reaches = pi.reaches_laptop and not tello_only
    dog_up = links["dog"].up and "dog" not in flapped
    drone_up = links["drone"].up and "drone" not in flapped
    pi_up = pi.up and "pi" not in flapped
    internet_up = links["internet"].up and "internet" not in flapped
    simulated_links = any(item.simulated for item in links.values())
    real_untrusted = mode == "real" and (
        simulated_links or evidence != "physically_demonstrated"
    )
    pi_telemetry = (
        heartbeat and path_known and reaches and pi_up and not real_untrusted
    )
    rssi_armed = pi_telemetry
    handover = (switch_to is not None and switch_to != transport) or (
        fallback is not None and fallback != transport
    )
    request_safety = bool(flapped)
    detail = "ready:" + profile
    missing: str | None = None
    status = "ok"
    error_code: str | None = None
    recovery = False
    if handover:
        status, error_code, detail, missing = _block("transport_switch", "handover")
    elif not dog_identified:
        status, error_code, detail, missing = _block("dog_capabilities", "dog")
    elif not drone_identified:
        status, error_code, detail, missing = _block("drone_capabilities", "drone")
    elif transport == "ethernet" and tether_accepted is not True:
        status, error_code, detail, missing = _block("tether_acceptance", "tether")
    elif transport == "wifi" and wifi_accepted is not True:
        status, error_code, detail, missing = _block("wifi_acceptance", "wifi_acceptance")
    elif real_untrusted:
        status, error_code, detail, missing = _block("simulated_probe", "probe")
    elif not dog_up:
        status, error_code, detail, missing = _down("dog", "dog" in flapped)
        recovery = "dog" in flapped
    elif not drone_up:
        status, error_code, detail, missing = _down("drone", "drone" in flapped)
        recovery = "drone" in flapped
    elif not internet_up:
        status, error_code, detail, missing = _down("internet", "internet" in flapped)
        recovery = "internet" in flapped
    elif not path_known:
        status, error_code, detail, missing = _block("pi_path", "pi_path")
    elif tello_only or not pi.reaches_laptop:
        status, error_code, detail, missing = _block("pi_data_path", "pi_data_path")
    elif not heartbeat:
        status, error_code, detail, missing = _block("pi_heartbeat", "pi_heartbeat")
    elif not pi_up:
        status, error_code, detail, missing = _down("pi", "pi" in flapped)
        recovery = "pi" in flapped
    ready = status == "ok"
    router_note = "back_enclosure_failed" if router_failed else "not_in_ready_check"
    extras: list[str] = []
    if _sensitive(probe):
        extras.append("secrets:redacted")
    if dog_identified:
        extras.append("dog_rssi_receiver:ignored")
    if heartbeat and not path_known:
        extras.append("heartbeat:ignored_without_path")
    if tello_only and not path_known:
        extras.append("tello_ap:not_a_pi_path")
    if path_known and (tello_only or not pi.reaches_laptop):
        extras.append("tello_ap:not_a_laptop_route")
    if handover:
        extras.append("handover:rejected")
    if switch_to is not None and switch_to != transport:
        extras.append(f"switch:{switch_to}")
    if fallback is not None and fallback != transport:
        extras.append(f"fallback:{fallback}")
    extras.extend(f"flap:{name}" for name in LINKS if name in flapped)
    if request_safety:
        extras.append("request_safety:true")
        extras.append("latch:task28")
    trace = (
        f"profile:{profile}",
        f"transport:{transport}",
        f"mode:{mode}",
        f"pi_path:{pi_path if pi_path is not None else 'missing'}",
        f"dog:{'up' if dog_up else 'down'}",
        f"drone:{'up' if drone_up else 'down'}",
        f"pi:{'up' if pi_up else 'down'}",
        f"internet:{'up' if internet_up else 'down'}",
        f"dog_identified:{_yn(dog_identified)}",
        f"drone_identified:{_yn(drone_identified)}",
        f"pi_telemetry:{_yn(pi_telemetry)}",
        f"tether:{_tether_label(transport, tether_accepted)}",
        f"wifi_acceptance:{_wifi_label(transport, wifi_accepted)}",
        f"router:{router_note}",
        "router_is_not_pi:true",
        f"rssi:{'armed' if rssi_armed else 'blocked'}",
        f"ready:{_yn(ready)}",
        f"evidence:{evidence}",
        "sockets:none",
        *extras,
    )
    event_kind = "state_changed"
    if request_safety:
        event_kind = "link_lost"
    elif handover or status == "failed":
        event_kind = "composition_rejected"
    return LinkReport(
        status="ok" if ready else status,
        detail=detail,
        error_code=None if ready else error_code,
        recovery_required=recovery,
        trace=trace,
        event_kind=event_kind,
        ready=ready,
        profile_name=profile,
        dog_transport=transport,
        pi_path=pi_path,
        rssi_blocked=not rssi_armed,
        missing_path=None if ready else missing,
        dog_identified=dog_identified,
        drone_identified=drone_identified,
        pi_telemetry=pi_telemetry,
        router_note=router_note,
        request_safety=request_safety,
        evidence=evidence,
        simulated=not (ready and evidence == "physically_demonstrated"),
    )


class _BadProbe(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class _Link:
    up: bool
    simulated: bool
    joined_tello_ap_only: bool = False
    reaches_laptop: bool = True


def _early(detail: str) -> LinkReport:
    token = detail.removeprefix("blocked:")
    return LinkReport(
        status="failed",
        detail=detail,
        error_code="invalid_input",
        recovery_required=False,
        trace=("rejected", token, "sockets:none"),
        event_kind="composition_rejected",
        ready=False,
        profile_name="",
        dog_transport="",
        pi_path=None,
        rssi_blocked=True,
        missing_path=token,
        dog_identified=False,
        drone_identified=False,
        pi_telemetry=False,
        router_note="not_in_ready_check",
        request_safety=False,
        evidence="simulated",
        simulated=True,
    )


def _forbidden(action: str) -> LinkReport:
    route_actions = {"change_route", "add_route", "delete_route", "route_add"}
    detail = "blocked:route_change" if action in route_actions else "blocked:forbidden_action"
    return LinkReport(
        status="failed",
        detail=detail,
        error_code="forbidden_command",
        recovery_required=False,
        trace=(f"action:{action}", "repair:rejected", "ready:false", "sockets:none"),
        event_kind="composition_rejected",
        ready=False,
        profile_name="",
        dog_transport="",
        pi_path=None,
        rssi_blocked=True,
        missing_path="route",
        dog_identified=False,
        drone_identified=False,
        pi_telemetry=False,
        router_note="not_in_ready_check",
        request_safety=False,
        evidence="simulated",
        simulated=True,
    )


def _block(
    reason: str, missing: str
) -> tuple[str, str, str, str]:
    return ("blocked", "rejected", f"blocked:{reason}", missing)


def _down(link: str, flapped: bool) -> tuple[str, str, str, str]:
    code = "unavailable" if flapped else "rejected"
    return ("blocked", code, f"blocked:{link}_link", link)


def _sensitive(probe: Mapping[str, object]) -> bool:
    return any(key in probe for key in SENSITIVE_KEYS)


def _profile(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _BadProbe("blocked:profile_name")
    if len(value) > 40 or not value.replace("-", "").isalnum() or not value[0].isalpha():
        raise _BadProbe("blocked:profile_name")
    if not value.isascii() or not value.islower():
        raise _BadProbe("blocked:profile_name")
    return value


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _BadProbe(f"blocked:{label}")
    return value


def _pi_path(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in PI_PATHS:
        raise _BadProbe("blocked:unknown_pi_path")
    return value


def _flag(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise _BadProbe(f"blocked:{label}")
    return value


def _optional_flag(probe: Mapping[str, object], key: str) -> bool | None:
    if key not in probe:
        return None
    return _flag(probe[key], f"{key}_type")


def _optional_transport(probe: Mapping[str, object], key: str) -> str | None:
    if key not in probe or probe[key] is None:
        return None
    return _choice(probe[key], TRANSPORTS, key)


def _actions(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _BadProbe("blocked:actions")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise _BadProbe("blocked:actions")
        if item not in ALLOWED_ACTIONS and item not in FORBIDDEN_ACTIONS:
            raise _BadProbe("blocked:unknown_action")
        names.append(item)
    return tuple(names)


def _flapped(value: object) -> frozenset[str]:
    if isinstance(value, tuple):
        items = list(value)
    elif isinstance(value, list):
        items = value
    else:
        raise _BadProbe("blocked:flapped")
    names: list[str] = []
    for item in items:
        if not isinstance(item, str) or item not in LINKS:
            raise _BadProbe("blocked:flapped")
        names.append(item)
    return frozenset(names)


def _links(value: object) -> dict[str, _Link]:
    raw = _mapping(value, "links")
    if set(raw) != set(LINKS):
        raise _BadProbe("blocked:links")
    found: dict[str, _Link] = {}
    for name in LINKS:
        body = _mapping(raw[name], name)
        allowed = {"up", "simulated"}
        if name == "pi":
            allowed = {"up", "simulated", "joined_tello_ap_only", "reaches_laptop"}
        extra = [key for key in body if key not in allowed]
        if extra:
            raise _BadProbe("blocked:links")
        joined = False
        reaches = True
        if name == "pi":
            if "joined_tello_ap_only" in body:
                joined = _flag(body["joined_tello_ap_only"], "tello_flag")
            if "reaches_laptop" in body:
                reaches = _flag(body["reaches_laptop"], "reaches_laptop")
        found[name] = _Link(
            up=_flag(body.get("up"), f"{name}_up"),
            simulated=_flag(body.get("simulated"), f"{name}_simulated"),
            joined_tello_ap_only=joined,
            reaches_laptop=reaches,
        )
    return found


def _messages(value: object) -> dict[str, object]:
    if value is None:
        return {}
    return dict(_mapping(value, "messages"))


def _peer(message: object, source: str, kind: str) -> bool:
    if not isinstance(message, Mapping):
        return False
    if message.get("protocol_version") != "2.0-draft":
        return False
    if message.get("source") != source or message.get("kind") != kind:
        return False
    if message.get("destination") != "ground":
        return False
    if not isinstance(message.get("simulated"), bool):
        return False
    payload = message.get("payload")
    if not isinstance(payload, Mapping):
        return False
    device = payload.get("device_id")
    if not isinstance(device, str) or not device:
        return False
    if kind == "heartbeat":
        return isinstance(payload.get("healthy"), bool)
    return payload.get("role") == source


def _mapping(value: object, label: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    raise _BadProbe(f"blocked:{label}")


def _tether_label(transport: str, accepted: bool | None) -> str:
    if transport != "ethernet":
        return "not_required"
    if accepted is True:
        return "accepted"
    return "missing"


def _wifi_label(transport: str, accepted: bool | None) -> str:
    if transport != "wifi":
        return "not_required" if accepted is not True else "accepted"
    if accepted is True:
        return "accepted"
    return "missing"


def _yn(value: bool) -> str:
    if value:
        return "true"
    return "false"


def _fixture(name: str) -> Path:
    return repo_root() / "fixtures" / "ground" / "g30" / name


def _load(name: str) -> dict[str, object]:
    try:
        text = _fixture(name).read_text(encoding="utf-8")
    except OSError as exc:
        raise fault("io_fault", f"{name} could not be read", recovery_required=True) from exc
    try:
        parsed: object = json.loads(text)
    except ValueError as exc:
        raise fault("invalid_input", f"{name} is not valid json") from exc
    if not isinstance(parsed, dict):
        raise fault("invalid_input", f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _clone(name: str) -> dict[str, object]:
    parsed: object = json.loads(json.dumps(_load(name)))
    if not isinstance(parsed, dict):
        raise fault("invalid_input", f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _acceptance(name: str) -> bool:
    accepted = _load(name).get("accepted")
    if not isinstance(accepted, bool):
        raise fault("invalid_input", f"{name} acceptance must be a boolean")
    return accepted


def _with_messages(probe: dict[str, object], *, pi: bool) -> dict[str, object]:
    messages: dict[str, object] = {
        "dog": _load("dog-capabilities.json"),
        "drone": _load("drone-capabilities.json"),
    }
    if pi:
        messages["pi"] = _load("pi-heartbeat.json")
    probe["messages"] = messages
    return probe


def _ethernet() -> dict[str, object]:
    probe = _clone("probe-ethernet.json")
    probe["tether_accepted"] = _acceptance("tether-acceptance.json")
    probe["wifi_accepted"] = False
    return _with_messages(probe, pi=True)


def _wifi() -> dict[str, object]:
    probe = _clone("probe-wifi.json")
    probe["tether_accepted"] = False
    probe["wifi_accepted"] = _acceptance("wifi-acceptance.json")
    return _with_messages(probe, pi=True)


def _replace_link(probe: dict[str, object], name: str, **fields: object) -> None:
    links = probe.get("links")
    if not isinstance(links, dict):
        raise fault("invalid_input", "links are missing")
    current = links.get(name)
    if not isinstance(current, dict):
        raise fault("invalid_input", f"{name} link is missing")
    updated = {str(key): value for key, value in current.items()}
    updated.update(fields)
    links[name] = updated


def _case_no_tether() -> dict[str, object]:
    probe = _ethernet()
    probe["tether_accepted"] = _acceptance("tether-missing.json")
    return probe


def _case_missing_pi() -> dict[str, object]:
    probe = _ethernet()
    probe["pi_path"] = None
    return probe


def _case_tello_only() -> dict[str, object]:
    probe = _ethernet()
    probe["pi_path"] = None
    _replace_link(probe, "pi", joined_tello_ap_only=True, reaches_laptop=False)
    return probe


def _case_switch() -> dict[str, object]:
    probe = _ethernet()
    probe["switch_to"] = "wifi"
    return probe


def _case_dog_drop() -> dict[str, object]:
    probe = _ethernet()
    probe["flapped"] = ["dog"]
    return probe


def _case_route() -> dict[str, object]:
    probe = _ethernet()
    probe["actions"] = ["change_route"]
    return probe


def _case_secrets() -> dict[str, object]:
    probe = _ethernet()
    probe["password"] = _load("secret-marker.json")["marker"]
    probe["sensitive_values"] = [probe["password"]]
    return probe


def _case_wifi_missing() -> dict[str, object]:
    probe = _wifi()
    probe["wifi_accepted"] = False
    return probe


def _case_fallback() -> dict[str, object]:
    probe = _ethernet()
    _replace_link(probe, "dog", up=False)
    probe["fallback_transport"] = "wifi"
    return probe


def _case_real_simulated() -> dict[str, object]:
    probe = _ethernet()
    probe["probe_mode"] = "real"
    probe["evidence"] = "simulated"
    return probe


def _case_physical_claim() -> dict[str, object]:
    probe = _ethernet()
    probe["evidence"] = "physically_demonstrated"
    return probe


def _case_string_tether() -> dict[str, object]:
    probe = _ethernet()
    probe["tether_accepted"] = "true"
    return probe


def _case_pi_down() -> dict[str, object]:
    probe = _ethernet()
    _replace_link(probe, "pi", up=False)
    return probe


def _case_internet_down() -> dict[str, object]:
    probe = _ethernet()
    _replace_link(probe, "internet", up=False)
    return probe


def _case_not_simultaneous() -> dict[str, object]:
    probe = _ethernet()
    probe["sequential"] = True
    return probe


def _case_router_without_pi() -> dict[str, object]:
    probe = _ethernet()
    probe["pi_path"] = None
    probe["router_failed"] = True
    return probe


def _case_unknown_path() -> dict[str, object]:
    probe = _ethernet()
    probe["pi_path"] = "tello_ap"
    return probe


def _case_pi_data_path() -> dict[str, object]:
    probe = _ethernet()
    _replace_link(probe, "pi", joined_tello_ap_only=True, reaches_laptop=False)
    return probe


def _register() -> dict[str, Callable[[], dict[str, object]]]:
    return {
        "ethernet_ready": _ethernet,
        "router_separate": _ethernet,
        "ethernet_no_tether": _case_no_tether,
        "missing_pi_path": _case_missing_pi,
        "tello_without_pi": _case_tello_only,
        "transport_switch": _case_switch,
        "dog_link_drop": _case_dog_drop,
        "route_change": _case_route,
        "secrets_redacted": _case_secrets,
        "wifi_ready": _wifi,
        "wifi_no_acceptance": _case_wifi_missing,
        "no_fallback": _case_fallback,
        "simulated_real_mode": _case_real_simulated,
        "physical_claim": _case_physical_claim,
        "string_tether": _case_string_tether,
        "pi_link_down": _case_pi_down,
        "internet_down": _case_internet_down,
        "not_simultaneous": _case_not_simultaneous,
        "router_not_pi_excuse": _case_router_without_pi,
        "unknown_pi_path": _case_unknown_path,
        "pi_data_path": _case_pi_data_path,
    }


_CASES: dict[str, Callable[[], dict[str, object]]] = _register()
