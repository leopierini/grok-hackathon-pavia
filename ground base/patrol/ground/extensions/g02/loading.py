"""Load and normalize Ground configuration. This module does not open adapters."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, cast

from patrol.ground.kernel.catalog import DOG_TRANSPORTS, LAUNCH_TIERS, MODES, SCENARIOS, ZONES
from patrol.ground.kernel.contracts import GroundSettings, IOPort
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings, redact
from patrol.ground.kernel.validation import freeze_map

MAX_CONFIG_BYTES = 262_144
DRONE_SDK = "DJITelloPy"
DRONE_RADIO = "wifi"
CONNECTION_MODES = frozenset({"LocalSTA", "LocalAP", "Remote"})
PAD_TIERS = frozenset({"carried_pad", "stationary_pad"})
_IDENTITY = re.compile(r"[A-Za-z0-9._-]{1,80}")
_SECRET_PARTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "authorization",
    "aes_128",
    "aes_key",
)
_GROUND_KEYS = frozenset(
    {
        "zones",
        "dog_config_path",
        "drone_config_path",
        "grok_config_path",
        "dog_profile_paths",
        "dog_transport",
        "profile_identity",
        "profile_by_zone",
        "launch_tier",
        "arrival_timeout_s",
        "flight_ready_timeout_s",
        "incident_timeout_s",
        "route_limit_s",
        "flight_limit_s",
        "model_limit_s",
        "prepare_limit_s",
        "capture_limit_s",
        "connect_limit_s",
        "output_root",
        "scenario",
    }
)
_REAL_GROUND_KEYS = (
    "zones",
    "launch_tier",
    "arrival_timeout_s",
    "flight_ready_timeout_s",
    "incident_timeout_s",
    "output_root",
)
_TIMEOUTS: dict[str, float] = {
    "arrival_timeout_s": 15.0,
    "flight_ready_timeout_s": 30.0,
    "incident_timeout_s": 180.0,
    "route_limit_s": 30.0,
    "flight_limit_s": 30.0,
    "model_limit_s": 20.0,
    "prepare_limit_s": 10.0,
    "capture_limit_s": 10.0,
    "connect_limit_s": 10.0,
}
_SAFE_CAPABILITY = (
    "flight_capability",
    "flight_disabled_reason",
    "physical_acceptance",
    "drone_sdk",
    "drone_radio",
    "route_capability",
    "route_disabled_reason",
    "transport_explicit",
    "wifi_configured",
    "ethernet_configured",
    "launch_tier_explicit",
    "drone_config_present",
    "dog_config_present",
    "grok_config_present",
    "vendor_connection_mode",
)


@dataclass
class LoadedAdapter:
    body: dict[str, object]
    scenario: str | None = None
    connection_mode: str | None = None
    route_configured: bool = False
    reserve: int | None = None
    profiles_configured: bool = False
    present: bool = False


def load_settings(
    io: IOPort,
    path: str | Path | None,
    *,
    modes: Mapping[str, str],
    scenario: str | None,
) -> GroundSettings:
    return ConfigLoader(io).load(path, modes=modes, scenario=scenario)


def safe_capability_keys() -> tuple[str, ...]:
    return _SAFE_CAPABILITY


def redacted_view(settings: GroundSettings) -> Mapping[str, object]:
    """Journal view. Adapter payloads and credential values stay out of it."""
    view: dict[str, object] = dict(redact(settings))
    capability = settings.adapter_configs.get("capability")
    if isinstance(capability, Mapping):
        for key in _SAFE_CAPABILITY:
            if key in capability:
                view[key] = capability[key]
    frozen = freeze_map(view)
    rendered = json.dumps(_unwrap(frozen), sort_keys=True)
    for secret in secret_values(settings):
        if secret and secret in rendered:
            raise fault("validation_failed", "redacted view leaked a secret")
    return frozen


def secret_values(settings: GroundSettings) -> tuple[str, ...]:
    found: list[str] = []
    _collect(settings.adapter_configs, found)
    return tuple(dict.fromkeys(found))


def canonical_settings(settings: GroundSettings) -> str:
    payload = {
        "zones": list(settings.zones),
        "profile_by_zone": {
            key: settings.profile_by_zone[key] for key in sorted(settings.profile_by_zone)
        },
        "launch_tier": settings.launch_tier,
        "dog_transport": settings.dog_transport,
        "profile_identity": settings.profile_identity,
        "timeouts": {
            "arrival_timeout_s": settings.arrival_timeout_s,
            "flight_ready_timeout_s": settings.flight_ready_timeout_s,
            "incident_timeout_s": settings.incident_timeout_s,
            "route_limit_s": settings.route_limit_s,
            "flight_limit_s": settings.flight_limit_s,
            "model_limit_s": settings.model_limit_s,
            "prepare_limit_s": settings.prepare_limit_s,
            "capture_limit_s": settings.capture_limit_s,
            "connect_limit_s": settings.connect_limit_s,
        },
        "output_root": settings.output_root,
        "modes": {key: settings.modes[key] for key in sorted(settings.modes)},
        "scenario": settings.scenario,
        "adapters": _unwrap(settings.adapter_configs),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ConfigLoader:
    def __init__(self, io: IOPort) -> None:
        self.io = io
        self.secrets: list[str] = []

    def load(
        self,
        path: str | Path | None,
        *,
        modes: Mapping[str, str],
        scenario: str | None,
    ) -> GroundSettings:
        selected = self._modes(modes)
        override = None if scenario is None else self._scenario(scenario)
        if path is None:
            return self._defaults(selected, override)
        if not isinstance(path, (str, Path)) or (isinstance(path, str) and not path):
            self._fail("invalid_input", "configuration path must be a file path")
        source = Path(path)
        document = self._read_object(source, source.name or "configuration")
        return self._from_document(source, document, selected, override)

    def _defaults(self, modes: dict[str, str], override: str | None) -> GroundSettings:
        if any(mode == "real" for mode in modes.values()):
            self._fail("invalid_input", "real mode requires a configuration file")
        chosen = override or "blocked_resolved"
        output = str((repo_root() / "artifacts").resolve())
        return self._assemble(
            modes=modes,
            zones=("entrance", "room_2", "display"),
            profiles={"room_2": "room_2_view_v1"},
            launch_tier="floor",
            launch_explicit=False,
            transport="ethernet",
            transport_explicit=False,
            identity="dog.ethernet",
            timeouts=dict(_TIMEOUTS),
            output_root=output,
            scenario=chosen,
            dog=self._empty_adapter(chosen),
            drone=self._empty_adapter(chosen),
            grok=self._empty_adapter(chosen),
            dog_file=False,
            drone_file=False,
            grok_file=False,
            ethernet_configured=False,
            wifi_configured=False,
        )

    def _from_document(
        self,
        source: Path,
        document: dict[str, object],
        modes: dict[str, str],
        override: str | None,
    ) -> GroundSettings:
        unknown = sorted(key for key in document if key not in _GROUND_KEYS)
        if unknown:
            self._fail("invalid_input", "unknown ground setting: " + ", ".join(unknown))
        real = any(mode == "real" for mode in modes.values())
        if real:
            for key in _REAL_GROUND_KEYS:
                if key not in document:
                    self._fail(
                        "invalid_input",
                        f"{key} is required when a real adapter is selected",
                    )
        zones = (
            self._zones(document["zones"])
            if "zones" in document
            else ("entrance", "room_2", "display")
        )
        launch_explicit = "launch_tier" in document
        launch = self._choice(document.get("launch_tier", "floor"), LAUNCH_TIERS, "launch_tier")
        if launch in PAD_TIERS and modes["drone"] == "real" and modes["dog"] == "fake":
            self._fail("invalid_input", "real pad launch cannot use a fake dog")
        transport_explicit = "dog_transport" in document
        transport = self._choice(
            document.get("dog_transport", "ethernet"),
            DOG_TRANSPORTS,
            "dog_transport",
        )
        timeouts = {
            key: self._positive(document[key], key) if key in document else default
            for key, default in _TIMEOUTS.items()
        }
        if "output_root" in document:
            output = self._resolve_path(source, document["output_root"], "output_root")
        elif real:
            self._fail("invalid_input", "output_root is required when a real adapter is selected")
        else:
            output = (source.parent / "artifacts").resolve()
        if output.is_file():
            self._fail("invalid_input", "output root is a file")
        if modes["drone"] == "real" and "profile_by_zone" not in document:
            self._fail("invalid_input", "profile_by_zone is required when drone mode is real")
        if "profile_by_zone" in document:
            profiles = self._profiles(document["profile_by_zone"], zones)
        elif "room_2" not in zones:
            self._fail("invalid_input", "profile_by_zone is required when room_2 is not configured")
        else:
            profiles = {"room_2": "room_2_view_v1"}
        file_scenario = self._scenario(document["scenario"]) if "scenario" in document else None
        identity = self._identity(document.get("profile_identity"), transport)
        profile_paths = self._profile_paths(source, document.get("dog_profile_paths"))
        dog_path = self._selected_adapter_path(
            source,
            document.get("dog_config_path"),
            "dog_config_path",
            profile_paths.get(transport),
            required=modes["dog"] == "real",
        )
        drone_path = self._optional_adapter_path(
            source,
            document.get("drone_config_path"),
            "drone_config_path",
            required=modes["drone"] == "real",
        )
        grok_path = self._optional_adapter_path(
            source,
            document.get("grok_config_path"),
            "grok_config_path",
            required=modes["grok"] == "real",
        )
        dog = self._load_dog(dog_path, modes["dog"]) if dog_path is not None else None
        drone = self._load_drone(drone_path, modes["drone"]) if drone_path is not None else None
        grok = self._load_grok(grok_path, modes["grok"]) if grok_path is not None else None
        for profile_path in profile_paths.values():
            if dog_path is not None and profile_path.resolve() == dog_path.resolve():
                continue
            self._load_dog(profile_path, "fake")
        chosen = self._shared_scenario(override, file_scenario, (dog, drone, grok), modes)
        self._reject_secret("output_root", str(output))
        self._reject_secret("profile_identity", identity)
        self._reject_secret("scenario", chosen)
        for profile_id in profiles.values():
            self._reject_secret("profile id", profile_id)
        dog_body = self._finish_adapter(dog, modes["dog"], chosen)
        drone_body = self._finish_adapter(drone, modes["drone"], chosen)
        grok_body = self._finish_adapter(grok, modes["grok"], chosen)
        ethernet_configured = "ethernet" in profile_paths or (
            transport == "ethernet" and dog_path is not None
        )
        wifi_configured = "wifi" in profile_paths or (
            transport == "wifi" and dog_path is not None
        )
        return self._assemble(
            modes=modes,
            zones=zones,
            profiles=profiles,
            launch_tier=launch,
            launch_explicit=launch_explicit,
            transport=transport,
            transport_explicit=transport_explicit,
            identity=identity,
            timeouts=timeouts,
            output_root=str(output),
            scenario=chosen,
            dog=dog_body,
            drone=drone_body,
            grok=grok_body,
            dog_file=dog_path is not None,
            drone_file=drone_path is not None,
            grok_file=grok_path is not None,
            ethernet_configured=ethernet_configured,
            wifi_configured=wifi_configured,
            dog_loaded=dog,
            drone_loaded=drone,
        )

    def _assemble(
        self,
        *,
        modes: dict[str, str],
        zones: tuple[str, ...],
        profiles: dict[str, str],
        launch_tier: str,
        launch_explicit: bool,
        transport: str,
        transport_explicit: bool,
        identity: str,
        timeouts: dict[str, float],
        output_root: str,
        scenario: str,
        dog: dict[str, object],
        drone: dict[str, object],
        grok: dict[str, object],
        dog_file: bool,
        drone_file: bool,
        grok_file: bool,
        ethernet_configured: bool,
        wifi_configured: bool,
        dog_loaded: LoadedAdapter | None = None,
        drone_loaded: LoadedAdapter | None = None,
    ) -> GroundSettings:
        flight, flight_reason = _flight_capability(modes["drone"], drone_loaded)
        if not drone_file and modes["drone"] != "real":
            flight, flight_reason = "disabled", "optional_config_absent"
        if dog_loaded is not None and dog_loaded.route_configured:
            route, route_reason = "configured", ""
        else:
            route, route_reason = "disabled", "route_unset"
        capability: dict[str, object] = {
            "flight_capability": flight,
            "flight_disabled_reason": flight_reason,
            "physical_acceptance": "not_accepted",
            "drone_sdk": DRONE_SDK,
            "drone_radio": DRONE_RADIO,
            "route_capability": route,
            "route_disabled_reason": route_reason,
            "transport_explicit": transport_explicit,
            "wifi_configured": wifi_configured,
            "ethernet_configured": ethernet_configured,
            "launch_tier_explicit": launch_explicit,
            "drone_config_present": drone_file,
            "dog_config_present": dog_file,
            "grok_config_present": grok_file,
            "vendor_connection_mode": ""
            if dog_loaded is None or dog_loaded.connection_mode is None
            else dog_loaded.connection_mode,
        }
        drone = dict(drone)
        drone.setdefault("sdk", DRONE_SDK)
        drone.setdefault("radio_transport", DRONE_RADIO)
        configs = {
            "capability": _frozen_map(capability),
            "dog": _frozen_map(dog),
            "drone": _frozen_map(drone),
            "grok": _frozen_map(grok),
        }
        try:
            return make_settings(
                zones=zones,
                profile_by_zone=profiles,
                launch_tier=launch_tier,
                dog_transport=transport,
                profile_identity=identity,
                arrival_timeout_s=timeouts["arrival_timeout_s"],
                flight_ready_timeout_s=timeouts["flight_ready_timeout_s"],
                incident_timeout_s=timeouts["incident_timeout_s"],
                route_limit_s=timeouts["route_limit_s"],
                flight_limit_s=timeouts["flight_limit_s"],
                model_limit_s=timeouts["model_limit_s"],
                prepare_limit_s=timeouts["prepare_limit_s"],
                capture_limit_s=timeouts["capture_limit_s"],
                connect_limit_s=timeouts["connect_limit_s"],
                output_root=output_root,
                adapter_configs=configs,
                modes=modes,
                scenario=scenario,
            )
        except GroundFault as exc:
            self._fail(exc.error.code, exc.error.detail, recovery=exc.error.recovery_required)

    def _shared_scenario(
        self,
        override: str | None,
        file_scenario: str | None,
        adapters: tuple[LoadedAdapter | None, ...],
        modes: dict[str, str],
    ) -> str:
        if override is not None:
            return override
        if file_scenario is not None:
            return file_scenario
        found: list[str] = []
        for item, mode in zip(adapters, ("dog", "drone", "grok"), strict=True):
            if item is None or modes[mode] != "fake" or item.scenario is None:
                continue
            found.append(item.scenario)
        unique = set(found)
        if len(unique) > 1:
            self._fail("invalid_input", "fake adapters declare different scenarios")
        if len(unique) == 1:
            return found[0]
        return "blocked_resolved"

    def _finish_adapter(
        self,
        loaded: LoadedAdapter | None,
        mode: str,
        scenario: str,
    ) -> dict[str, object]:
        if mode == "fake":
            body = {} if loaded is None else dict(loaded.body)
            body["scenario"] = scenario
            return body
        if loaded is None:
            return {}
        return dict(loaded.body)

    def _empty_adapter(self, scenario: str) -> dict[str, object]:
        return {"scenario": scenario}

    def _load_dog(self, path: Path, mode: str) -> LoadedAdapter:
        raw = self._read_object(path, path.name)
        if "dog_transport" in raw:
            self._fail("invalid_input", "dog transport is set in the ground file, not the dog file")
        body: dict[str, object] = {}
        connection: str | None = None
        if "connection_mode" in raw:
            connection = self._choice(raw["connection_mode"], CONNECTION_MODES, "connection_mode")
            body["connection_mode"] = connection
        elif mode == "real":
            self._fail("invalid_input", "connection_mode is required when dog mode is real")
        if "interface" in raw:
            body["interface"] = self._text(raw["interface"], "interface")
        elif mode == "real":
            self._fail("invalid_input", "interface is required when dog mode is real")
        route_configured = False
        if "routes_path" in raw:
            route = self._resolve_existing(path, raw["routes_path"], "dog routes_path")
            body["routes_path"] = str(route)
            route_configured = True
        self._timeout_field(raw, body, "max_route_s", required=mode == "real")
        self._timeout_field(raw, body, "command_timeout_s", required=mode == "real")
        scenario = self._optional_scenario(raw, mode)
        self._copy_private(raw, body, _DOG_PUBLIC)
        return LoadedAdapter(
            body=body,
            scenario=scenario,
            connection_mode=connection,
            route_configured=route_configured,
            present=True,
        )

    def _load_drone(self, path: Path, mode: str) -> LoadedAdapter:
        raw = self._read_object(path, path.name)
        body: dict[str, object] = {"sdk": DRONE_SDK, "radio_transport": DRONE_RADIO}
        if "sdk" in raw and raw["sdk"] != DRONE_SDK:
            self._fail("invalid_input", "drone sdk must be DJITelloPy")
        if "radio_transport" in raw and raw["radio_transport"] != DRONE_RADIO:
            self._fail("invalid_input", "Tello transport must be wifi")
        if "interface" in raw:
            body["interface"] = self._text(raw["interface"], "interface")
        elif mode == "real":
            self._fail("invalid_input", "interface is required when drone mode is real")
        profiles_configured = False
        if "profiles_path" in raw:
            profile = self._resolve_existing(path, raw["profiles_path"], "drone profiles_path")
            body["profiles_path"] = str(profile)
            profiles_configured = True
        reserve: int | None = None
        if "battery_min_percent" in raw:
            reserve = self._battery(raw["battery_min_percent"])
            if reserve is not None:
                body["battery_min_percent"] = reserve
        self._timeout_field(raw, body, "max_flight_s", required=mode == "real")
        self._timeout_field(raw, body, "command_timeout_s", required=mode == "real")
        scenario = self._optional_scenario(raw, mode)
        self._copy_private(raw, body, _DRONE_PUBLIC)
        return LoadedAdapter(
            body=body,
            scenario=scenario,
            reserve=reserve,
            profiles_configured=profiles_configured,
            present=True,
        )

    def _load_grok(self, path: Path, mode: str) -> LoadedAdapter:
        raw = self._read_object(path, path.name)
        body: dict[str, object] = {}
        if "model" in raw:
            body["model"] = self._text(raw["model"], "model")
        elif mode == "real":
            self._fail("invalid_input", "model is required when grok mode is real")
        if "prompt_version" in raw:
            body["prompt_version"] = self._text(raw["prompt_version"], "prompt_version")
        elif mode == "real":
            self._fail("invalid_input", "prompt_version is required when grok mode is real")
        self._timeout_field(raw, body, "request_timeout_s", required=mode == "real")
        scenario = self._optional_scenario(raw, mode)
        self._copy_private(raw, body, _GROK_PUBLIC)
        return LoadedAdapter(body=body, scenario=scenario, present=True)

    def _copy_private(
        self,
        raw: dict[str, object],
        body: dict[str, object],
        public: frozenset[str],
    ) -> None:
        for key, value in raw.items():
            if key in public:
                continue
            body[key] = self._json_copy(value, key)

    def _optional_scenario(self, raw: dict[str, object], mode: str) -> str | None:
        if "scenario" not in raw:
            return None
        if mode == "real":
            self._fail("invalid_input", "scenario is only valid for fake mode")
        return self._scenario(raw["scenario"])

    def _timeout_field(
        self,
        raw: dict[str, object],
        body: dict[str, object],
        key: str,
        *,
        required: bool,
    ) -> None:
        if key not in raw:
            if required:
                self._fail("invalid_input", f"{key} is required for this real adapter")
            return
        body[key] = self._positive(raw[key], key)

    def _profile_paths(self, source: Path, raw: object) -> dict[str, Path]:
        if raw is None:
            return {}
        if isinstance(raw, (str, bytes)) or not isinstance(raw, dict):
            self._fail("invalid_input", "dog_profile_paths must be an object")
        unknown = sorted(key for key in raw if key not in DOG_TRANSPORTS)
        if unknown:
            self._fail("invalid_input", "dog_profile_paths has an unknown transport")
        found: dict[str, Path] = {}
        for key in sorted(str(name) for name in raw):
            found[key] = self._resolve_existing(source, raw[key], f"dog_profile_paths.{key}")
        return found

    def _selected_adapter_path(
        self,
        source: Path,
        raw: object,
        label: str,
        mapped: Path | None,
        *,
        required: bool,
    ) -> Path | None:
        explicit = None if raw is None else self._resolve_existing(source, raw, label)
        if explicit is not None and mapped is not None and explicit.resolve() != mapped.resolve():
            self._fail(
                "invalid_input",
                "dog_config_path does not match the selected transport profile",
            )
        selected = explicit if explicit is not None else mapped
        if selected is None and required:
            self._fail("invalid_input", f"{label} is required when dog mode is real")
        return selected

    def _optional_adapter_path(
        self,
        source: Path,
        raw: object,
        label: str,
        *,
        required: bool,
    ) -> Path | None:
        if raw is None:
            if required:
                self._fail("invalid_input", f"{label} is required when that adapter mode is real")
            return None
        return self._resolve_existing(source, raw, label)

    def _identity(self, raw: object, transport: str) -> str:
        if raw is None:
            return f"dog.{transport}"
        if not isinstance(raw, str) or _IDENTITY.fullmatch(raw) is None:
            self._fail("invalid_input", "profile_identity has unsupported characters")
        self._reject_secret("profile_identity", raw)
        return raw

    def _modes(self, modes: Mapping[str, str]) -> dict[str, str]:
        if isinstance(modes, (str, bytes)) or not isinstance(modes, Mapping):
            self._fail("invalid_input", "modes must name dog, drone, and grok")
        copied: dict[str, object] = {}
        for key, value in modes.items():
            if not isinstance(key, str):
                self._fail("invalid_input", "modes must name dog, drone, and grok")
            copied[key] = value
        if set(copied) != {"dog", "drone", "grok"}:
            self._fail("invalid_input", "modes must name dog, drone, and grok")
        clean: dict[str, str] = {}
        for name in ("dog", "drone", "grok"):
            selected = copied[name]
            if not isinstance(selected, str) or selected not in MODES:
                self._fail("invalid_input", f"{name} mode must be fake or real")
            clean[name] = selected
        return clean

    def _zones(self, value: object) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, list):
            self._fail("invalid_input", "zones must be a list")
        if not value:
            self._fail("invalid_input", "zones must name at least one zone")
        names: list[str] = []
        for item in value:
            if not isinstance(item, str) or item not in ZONES:
                self._fail("invalid_input", "zones must use the frozen zone names")
            if item in names:
                self._fail("invalid_input", "zones contains a duplicate")
            names.append(item)
        return tuple(names)

    def _profiles(self, value: object, zones: tuple[str, ...]) -> dict[str, str]:
        if isinstance(value, (str, bytes)) or not isinstance(value, dict):
            self._fail("invalid_input", "profile_by_zone must be an object")
        if not value:
            self._fail("invalid_input", "profile_by_zone must name at least one zone")
        clean: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key not in ZONES:
                self._fail("invalid_input", "profile map contains an unknown zone")
            if key not in zones:
                self._fail("invalid_input", "profile map contains a zone that is not configured")
            if not isinstance(item, str) or not item or any(mark in item for mark in "/\\"):
                self._fail("invalid_input", "profile id must be an opaque name")
            self._reject_secret("profile id", item)
            clean[key] = item
        return clean

    def _choice(self, value: object, allowed: frozenset[str], label: str) -> str:
        if not isinstance(value, str) or value not in allowed:
            self._fail("invalid_input", f"{label} is not an allowed value")
        return value

    def _scenario(self, value: object) -> str:
        if not isinstance(value, str) or value not in SCENARIOS:
            self._fail("invalid_input", "unknown scenario")
        return value

    def _positive(self, value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._fail("invalid_input", f"{label} has the wrong JSON type")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            self._fail("invalid_input", f"{label} must be a positive finite number")
        return number

    def _battery(self, value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._fail("invalid_input", "battery_min_percent has the wrong JSON type")
        if isinstance(value, float) and not math.isfinite(value):
            self._fail("invalid_input", "battery_min_percent must be a positive finite number")
        if isinstance(value, float) and not value.is_integer():
            self._fail("invalid_input", "battery_min_percent must be a whole number")
        number = int(value)
        if number < 1 or number > 100:
            self._fail("invalid_input", "battery_min_percent must be from 1 to 100")
        return number

    def _text(self, value: object, label: str) -> str:
        if not isinstance(value, str) or not value:
            self._fail("invalid_input", f"{label} must be a non-empty string")
        self._reject_secret(label, value)
        return value

    def _read_object(self, path: Path, label: str) -> dict[str, object]:
        try:
            text = self.io.read_text(path, limit=MAX_CONFIG_BYTES)
        except GroundFault as exc:
            if exc.error.code == "invalid_input":
                self._fail("invalid_input", f"{label} is not utf-8")
            if exc.error.code == "validation_failed":
                self._fail("validation_failed", f"{label} exceeds the size limit")
            self._fail("io_fault", f"{label} could not be read", recovery=True)
        parsed = self._parse(text, label)
        _collect(parsed, self.secrets)
        return parsed

    def _parse(self, text: str, label: str) -> dict[str, object]:
        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if not isinstance(key, str):
                    self._fail("invalid_input", f"malformed JSON in {label}")
                if key in result:
                    self._fail("invalid_input", f"duplicate key {key} in {label}")
                result[key] = value
            return result

        def reject_constant(_constant: str) -> object:
            self._fail("invalid_input", f"nonfinite number in {label}")

        try:
            raw = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
        except GroundFault:
            raise
        except ValueError:
            self._fail("invalid_input", f"malformed JSON in {label}")
        if isinstance(raw, (str, bytes)) or not isinstance(raw, dict):
            self._fail("invalid_input", f"{label} must be a JSON object")
        return cast(dict[str, object], raw)

    def _resolve_path(self, declared_in: Path, raw: object, label: str) -> Path:
        if not isinstance(raw, str) or not raw:
            self._fail("invalid_input", f"{label} must be a path string")
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate.resolve()
        return (declared_in.parent / candidate).resolve()

    def _resolve_existing(self, declared_in: Path, raw: object, label: str) -> Path:
        resolved = self._resolve_path(declared_in, raw, label)
        if not resolved.is_file():
            self._fail("io_fault", f"{label} does not resolve", recovery=True)
        return resolved

    def _json_copy(self, value: object, label: str) -> object:
        if value is None or isinstance(value, str) or isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                self._fail("invalid_input", f"{label} must be a finite number")
            return value
        if isinstance(value, dict):
            copied: dict[str, object] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    self._fail("invalid_input", f"{label} has the wrong JSON type")
                copied[key] = self._json_copy(item, key)
            return copied
        if isinstance(value, list):
            return [self._json_copy(item, label) for item in value]
        self._fail("invalid_input", f"{label} has the wrong JSON type")

    def _reject_secret(self, label: str, value: str) -> None:
        for secret in self.secrets:
            if secret and secret in value:
                self._fail("invalid_input", f"{label} must not contain a credential")

    def _fail(self, code: str, detail: str, *, recovery: bool = False) -> NoReturn:
        raise fault(code, _scrub(detail, self.secrets), recovery_required=recovery)


_DOG_PUBLIC = frozenset(
    {
        "connection_mode",
        "interface",
        "routes_path",
        "max_route_s",
        "command_timeout_s",
        "scenario",
        "dog_transport",
    }
)
_DRONE_PUBLIC = frozenset(
    {
        "interface",
        "profiles_path",
        "battery_min_percent",
        "max_flight_s",
        "command_timeout_s",
        "scenario",
        "sdk",
        "radio_transport",
    }
)
_GROK_PUBLIC = frozenset({"model", "prompt_version", "request_timeout_s", "scenario"})


def _flight_capability(drone_mode: str, loaded: LoadedAdapter | None) -> tuple[str, str]:
    if drone_mode != "real":
        return "disabled", "fake_mode"
    if loaded is None or loaded.reserve is None:
        return "disabled", "reserve_unset"
    if not loaded.profiles_configured:
        return "disabled", "profile_unset"
    return "reserve_configured", ""


def _frozen_map(value: dict[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], _freeze(value))


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        frozen = {key: _freeze(value[key]) for key in sorted(value)}
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _unwrap(value: object) -> object:
    if isinstance(value, Mapping):
        ordered = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {str(key): _unwrap(item) for key, item in ordered}
    if isinstance(value, tuple):
        return [_unwrap(item) for item in value]
    return value


def _collect(value: object, found: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                isinstance(key, str)
                and isinstance(item, str)
                and _secret_key(key)
                and len(item) >= 8
            ):
                if item not in found:
                    found.append(item)
            _collect(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, found)


def _secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SECRET_PARTS)


def _scrub(detail: str, secrets: list[str]) -> str:
    cleaned = detail
    for secret in secrets:
        if secret and secret in cleaned:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned
