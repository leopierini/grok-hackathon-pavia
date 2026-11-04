"""Configuration port. The simulation harness calls create(services) and execute()."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from patrol.ground.extensions.g02.loading import (
    DRONE_RADIO,
    DRONE_SDK,
    canonical_settings,
    load_settings,
    safe_capability_keys,
    secret_values,
)
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundSettings,
    KernelContext,
    ServicePorts,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.settings import redact
from patrol.ground.kernel.validation import freeze_map

_FAKE = {"dog": "fake", "drone": "fake", "grok": "fake"}
_SECRET = "synthetic-secret-value"


class ConfigService:
    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        self.kernel = kernel
        self.peers = peers
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    def load(
        self,
        path: str | Path | None,
        *,
        modes: Mapping[str, str],
        scenario: str | None,
    ) -> GroundSettings:
        return load_settings(self.kernel.io, path, modes=modes, scenario=scenario)

    def redacted(self, settings: GroundSettings) -> Mapping[str, object]:
        if not isinstance(settings, GroundSettings):
            raise fault("invalid_input", "settings are required")
        view: dict[str, object] = dict(redact(settings))
        capability = settings.adapter_configs.get("capability")
        if isinstance(capability, Mapping):
            for key in safe_capability_keys():
                if key in capability:
                    view[key] = capability[key]
        encoded = json.dumps(view, sort_keys=True, default=str)
        for secret in secret_values(settings):
            if secret in encoded:
                raise fault("validation_failed", "redacted view leaked a secret")
        frozen = _immutable(view)
        if not isinstance(frozen, Mapping):
            raise fault("internal", "redacted view was not a mapping")
        return freeze_map(frozen)

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        handler = _CASES.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown config case")
        try:
            return await handler(self)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, device_calls=self._device_calls())

    def _device_calls(self) -> int:
        devices = getattr(self.peers.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if isinstance(calls, list):
            return len(calls)
        return 0

    def _live(self) -> int:
        devices = getattr(self.peers.adapters, "devices", None)
        live = getattr(devices, "live_call_count", 0)
        if isinstance(live, int) and not isinstance(live, bool):
            return live
        return 0

    def _hold(self, root: Path) -> None:
        self.cleanup_paths = (str(root),)

    def _expect_fault(
        self,
        action: Callable[[], object],
        code: str,
        detail_part: str,
        canonical: str,
    ) -> FeatureResult:
        try:
            action()
        except GroundFault as exc:
            leaked = _SECRET in exc.error.detail or _SECRET in str(exc)
            if exc.error.code != code or detail_part not in exc.error.detail or leaked:
                return _failed("validation_failed", "unexpected configuration error")
            return _failed(code, canonical, device_calls=self._device_calls())
        return _failed("validation_failed", "invalid configuration was accepted")


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> ConfigService:
    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "harness construction takes only services")
        return ConfigService(kernel.kernel, _ports(kernel))
    if peers is None:
        raise fault("invalid_input", "config provider requires kernel and peers")
    return ConfigService(kernel, peers)


def _ports(services: BaseServices) -> ServicePorts:
    return ServicePorts(
        config=services.config,
        state=services.state,
        journal=services.journal,
        executor=services.executor,
        evidence=services.evidence,
        console=services.console,
        adapters=services.adapters,
        workflow=services.workflow,
        safety=services.safety,
    )


async def _nested(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    route = root / "routes" / "room.json"
    _write(route, "SEGMENT not-a-trajectory\n")
    _write(root / "profiles" / "views.json", "profile-opaque\n")
    _write(
        root / "site" / "dog.json",
        json.dumps(
            {
                "connection_mode": "LocalSTA",
                "interface": "ethernet0",
                "routes_path": "../routes/room.json",
                "max_route_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    _write(
        root / "site" / "drone.json",
        json.dumps({"interface": "wifi0", "profiles_path": "../profiles/views.json"}),
    )
    _write(
        root / "site" / "grok.json",
        json.dumps({"model": "configured-model", "prompt_version": "v1", "request_timeout_s": 20}),
    )
    ground = root / "site" / "ground.json"
    _write(
        ground,
        json.dumps(
            {
                "zones": ["room_2"],
                "dog_config_path": "dog.json",
                "drone_config_path": "drone.json",
                "grok_config_path": "grok.json",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
                "output_root": "../out",
                "scenario": "blocked_resolved",
            }
        ),
    )
    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    previous = Path.cwd()
    try:
        os.chdir(elsewhere)
        settings = service.load(ground, modes=_FAKE, scenario=None)
    finally:
        os.chdir(previous)
    dog = _mapping(settings, "dog")
    drone = _mapping(settings, "drone")
    route_path = Path(str(dog.get("routes_path", "")))
    output = Path(settings.output_root)
    if (
        Path.cwd() == route_path.parent
        or route_path != route.resolve()
        or not output.is_absolute()
        or output != (root / "out").resolve()
        or dog.get("connection_mode") != "LocalSTA"
        or settings.dog_transport != "ethernet"
        or drone.get("sdk") != DRONE_SDK
        or drone.get("radio_transport") != DRONE_RADIO
        or settings.modes["dog"] != "fake"
        or service._device_calls() != 0
    ):
        return _failed("validation_failed", "nested paths were not normalized")
    return _ok(
        service,
        trace=(
            "cwd_independent",
            "routes_from_dog_file",
            "output_root_absolute",
            "transport:ethernet",
            "sdk:DJITelloPy",
            "radio:wifi",
        ),
        detail="normalized",
    )


async def _transports(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(root / "routes" / "room.json", "opaque\n")
    _write(
        root / "dog.ap.json",
        json.dumps(
            {
                "connection_mode": "LocalAP",
                "interface": "wlan-dog",
                "routes_path": "routes/room.json",
                "max_route_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    _write(
        root / "dog.sta.json",
        json.dumps(
            {
                "connection_mode": "LocalSTA",
                "interface": "ethernet0",
                "routes_path": "routes/room.json",
                "max_route_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    ethernet = root / "ethernet.json"
    wifi = root / "wifi.json"
    _write(
        ethernet,
        json.dumps(
            {
                "dog_config_path": "dog.ap.json",
                "dog_profile_paths": {"wifi": "dog.sta.json"},
                "zones": ["room_2"],
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    _write(
        wifi,
        json.dumps(
            {
                "dog_transport": "wifi",
                "dog_config_path": "dog.sta.json",
                "zones": ["room_2"],
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    wired = service.load(ethernet, modes=_FAKE, scenario=None)
    wireless = service.load(wifi, modes=dict(_FAKE), scenario=None)
    wired_dog = _mapping(wired, "dog")
    wireless_dog = _mapping(wireless, "dog")
    wired_cap = _mapping(wired, "capability")
    wireless_cap = _mapping(wireless, "capability")
    if (
        wired.dog_transport != "ethernet"
        or wired_dog.get("connection_mode") != "LocalAP"
        or wireless.dog_transport != "wifi"
        or wireless_dog.get("connection_mode") != "LocalSTA"
        or wired.modes != wireless.modes
        or wired_cap.get("physical_acceptance") != "not_accepted"
        or wireless_cap.get("physical_acceptance") != "not_accepted"
        or wireless_cap.get("wifi_configured") is not True
        or service._device_calls() != 0
    ):
        return _failed("validation_failed", "transport was inferred or armed")
    return _ok(
        service,
        trace=(
            "transport:ethernet",
            "transport:wifi",
            "physical_acceptance:not_accepted",
            "modes_unchanged",
            "vendor_mode_independent",
        ),
        detail="profiles",
    )


async def _malformed(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    path = root / "ground.json"
    _write(path, "{")
    return service._expect_fault(
        lambda: service.load(path, modes=_FAKE, scenario=None),
        "invalid_input",
        "malformed JSON",
        "malformed JSON rejected",
    )


async def _missing(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    path = root / "ground.json"
    _write(
        path,
        json.dumps(
            {
                "zones": ["room_2"],
                "launch_tier": "floor",
                "arrival_timeout_s": 15,
                "flight_ready_timeout_s": 30,
                "incident_timeout_s": 180,
                "output_root": "out",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    modes = {"dog": "real", "drone": "fake", "grok": "fake"}
    return service._expect_fault(
        lambda: service.load(path, modes=modes, scenario=None),
        "invalid_input",
        "dog_config_path",
        "missing key rejected",
    )


async def _nonfinite(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    path = root / "ground.json"
    _write(path, '{"zones": ["room_2"], "arrival_timeout_s": 1e309}')
    return service._expect_fault(
        lambda: service.load(path, modes=_FAKE, scenario=None),
        "invalid_input",
        "finite",
        "numeric limit rejected",
    )


async def _missing_route(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(
        root / "dog.json",
        json.dumps({"connection_mode": "LocalSTA", "routes_path": "missing.json"}),
    )
    path = root / "ground.json"
    _write(path, json.dumps({"dog_config_path": "dog.json", "zones": ["room_2"]}))
    return service._expect_fault(
        lambda: service.load(path, modes=_FAKE, scenario=None),
        "io_fault",
        "does not resolve",
        "path resolution rejected",
    )


async def _optional_flight(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(root / "routes" / "room.json", "opaque\n")
    _write(
        root / "dog.json",
        json.dumps(
            {
                "connection_mode": "LocalSTA",
                "interface": "ethernet0",
                "routes_path": "routes/room.json",
                "max_route_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    path = root / "ground.json"
    _write(
        path,
        json.dumps(
            {
                "zones": ["room_2"],
                "launch_tier": "floor",
                "arrival_timeout_s": 15,
                "flight_ready_timeout_s": 30,
                "incident_timeout_s": 180,
                "output_root": "out",
                "dog_config_path": "dog.json",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    modes = {"dog": "real", "drone": "fake", "grok": "fake"}
    settings = service.load(path, modes=modes, scenario=None)
    capability = _mapping(settings, "capability")
    if (
        settings.modes["dog"] != "real"
        or settings.modes["drone"] != "fake"
        or capability.get("flight_capability") != "disabled"
        or capability.get("flight_disabled_reason") != "optional_config_absent"
        or capability.get("drone_config_present") is not False
        or service._device_calls() != 0
    ):
        return _failed("validation_failed", "optional flight changed the requested mode")
    return _ok(
        service,
        trace=("flight:disabled", "drone_mode:fake", "dog_mode:real", "fallback:none"),
        detail="ground-only",
    )


async def _readiness(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(root / "routes" / "room.json", "opaque\n")
    _write(
        root / "dog.json",
        json.dumps(
            {
                "connection_mode": "LocalAP",
                "interface": "ethernet0",
                "routes_path": "routes/room.json",
                "max_route_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    path = root / "ground.json"
    _write(
        path,
        json.dumps(
            {
                "zones": ["room_2"],
                "launch_tier": "floor",
                "arrival_timeout_s": 15,
                "flight_ready_timeout_s": 30,
                "incident_timeout_s": 180,
                "output_root": "out",
                "dog_config_path": "dog.json",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    modes = {"dog": "real", "drone": "fake", "grok": "fake"}
    settings = service.load(path, modes=dict(modes), scenario=None)
    await service.peers.adapters.build(settings, settings.output_root, resolver={})
    dog = _mapping(settings, "dog")
    if (
        settings.dog_transport != "ethernet"
        or dog.get("connection_mode") != "LocalAP"
        or dict(settings.modes) != modes
        or service._device_calls() != 1
        or service._live() != 0
    ):
        return _failed("validation_failed", "readiness changed transport or mode")
    return _ok(
        service,
        trace=("transport:ethernet", "fallback:none", "adapters.build", "dog_mode:real"),
        detail="readiness",
    )


async def _secrets(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    valid = root / "valid.json"
    invalid = root / "invalid.json"
    grok = {
        "model": "configured-model",
        "prompt_version": "v1",
        "request_timeout_s": 20,
        "api_key": _SECRET,
    }
    _write(root / "grok.json", json.dumps(grok))
    _write(
        valid,
        json.dumps(
            {
                "zones": ["room_2"],
                "grok_config_path": "grok.json",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
            }
        ),
    )
    _write(
        invalid,
        json.dumps(
            {
                "zones": ["room_2"],
                "arrival_timeout_s": True,
                "api_key": _SECRET,
            }
        ),
    )
    try:
        service.load(invalid, modes=_FAKE, scenario=None)
    except GroundFault as exc:
        if _SECRET in exc.error.detail or _SECRET in str(exc):
            return _failed("validation_failed", "error detail leaked a secret")
        if exc.error.code != "invalid_input":
            return _failed("validation_failed", "unexpected configuration error")
    else:
        return _failed("validation_failed", "invalid configuration was accepted")
    settings = service.load(valid, modes=_FAKE, scenario=None)
    view = service.redacted(settings)
    encoded = json.dumps(dict(view), sort_keys=True, default=str)
    private = canonical_settings(settings)
    if _SECRET in encoded or _SECRET not in private or view.get("adapter_configs") != "redacted":
        return _failed("validation_failed", "redacted view leaked a secret")
    return _ok(service, trace=("secrets_absent",), detail="redacted")


async def _stable(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(root / "routes" / "room.json", "opaque\n")
    dog_a = root / "dog-a.json"
    dog_b = root / "dog-b.json"
    _write(
        dog_a,
        '{"connection_mode": "LocalSTA", "interface": "ethernet0", '
        '"routes_path": "routes/room.json"}',
    )
    _write(
        dog_b,
        '{"routes_path": "routes/room.json", "interface": "ethernet0", '
        '"connection_mode": "LocalSTA"}',
    )
    first = root / "first.json"
    second = root / "second.json"
    _write(
        first,
        '{"dog_config_path": "dog-a.json", "zones": ["room_2"], "launch_tier": "floor", '
        '"scenario": "dismiss"}',
    )
    _write(
        second,
        '{"scenario": "dismiss", "launch_tier": "floor", "zones": ["room_2"], '
        '"dog_config_path": "dog-b.json"}',
    )
    left = service.load(first, modes=_FAKE, scenario=None)
    right = service.load(second, modes=_FAKE, scenario=None)
    if canonical_settings(left) != canonical_settings(right):
        return _failed("validation_failed", "key order changed the normalized settings")
    return _ok(service, trace=("order_stable",), detail="stable")


async def _unchanged(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    dog = root / "dog.json"
    ground = root / "ground.json"
    _write(dog, '{"connection_mode": "Remote", "interface": "ethernet0"}\n')
    _write(ground, '{"dog_config_path": "dog.json", "zones": ["room_2"]}\n')
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dog, ground)}
    service.load(ground, modes=_FAKE, scenario="ground_clear")
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dog, ground)}
    partials = list(root.rglob("*.partial"))
    if before != after or partials:
        return _failed("validation_failed", "source configuration was rewritten")
    return _ok(service, trace=("source_unchanged",), detail="source")


async def _duplicate(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    path = root / "ground.json"
    _write(path, '{"zones": ["room_2"], "zones": ["display"]}')
    return service._expect_fault(
        lambda: service.load(path, modes=_FAKE, scenario=None),
        "invalid_input",
        "duplicate key",
        "duplicate key rejected",
    )


async def _pad(service: ConfigService) -> FeatureResult:
    root = _workspace(service)
    _write(root / "profiles" / "views.json", "opaque\n")
    _write(
        root / "drone.json",
        json.dumps(
            {
                "interface": "wifi0",
                "profiles_path": "profiles/views.json",
                "battery_min_percent": 40,
                "max_flight_s": 30,
                "command_timeout_s": 2,
            }
        ),
    )
    path = root / "ground.json"
    _write(
        path,
        json.dumps(
            {
                "zones": ["room_2"],
                "launch_tier": "carried_pad",
                "arrival_timeout_s": 15,
                "flight_ready_timeout_s": 30,
                "incident_timeout_s": 180,
                "output_root": "out",
                "profile_by_zone": {"room_2": "room_2_view_v1"},
                "drone_config_path": "drone.json",
            }
        ),
    )
    modes = {"dog": "fake", "drone": "real", "grok": "fake"}
    return service._expect_fault(
        lambda: service.load(path, modes=modes, scenario=None),
        "invalid_input",
        "fake dog",
        "pad combination rejected",
    )


def _workspace(service: ConfigService) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ground-g02-"))
    service._hold(root)
    return root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mapping(settings: GroundSettings, name: str) -> Mapping[str, object]:
    value = settings.adapter_configs.get(name)
    if isinstance(value, Mapping):
        return value
    return {}


def _ok(
    service: ConfigService,
    *,
    trace: tuple[str, ...],
    detail: str,
) -> FeatureResult:
    return FeatureResult(
        "ok",
        freeze_map(
            {
                "trace": trace,
                "detail": detail,
                "device_calls": service._device_calls(),
                "live_call_count": service._live(),
                "simulated": True,
                "authorized": False,
                "slot": "base.config",
                "schema_version": SCHEMA_VERSION,
            }
        ),
        (),
        None,
    )


def _failed(code: str, detail: str, **extra: object) -> FeatureResult:
    payload: dict[str, object] = {
        "device_calls": extra.pop("device_calls", 0),
        "detail": detail,
        "live_call_count": 0,
    }
    payload.update(extra)
    recovery = code in {"io_fault", "cancelled", "timeout"}
    return FeatureResult(
        "failed",
        freeze_map(payload),
        (),
        GroundError(code, detail, recovery),
    )


def _immutable(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _immutable(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_immutable(item) for item in value)
    return value


_CASES: dict[str, Callable[[ConfigService], Awaitable[FeatureResult]]] = {
    "nested_absolute_paths": _nested,
    "transport_profiles": _transports,
    "malformed_json": _malformed,
    "missing_real_keys": _missing,
    "nonfinite_limits": _nonfinite,
    "path_resolution_failure": _missing_route,
    "optional_flight_disabled": _optional_flight,
    "readiness_no_fallback": _readiness,
    "redacted_secrets": _secrets,
    "stable_key_order": _stable,
    "source_not_rewritten": _unchanged,
    "duplicate_key": _duplicate,
    "pad_fake_dog": _pad,
}
