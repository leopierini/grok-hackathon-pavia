"""Dog and drone seams for the museum story.

Fake mode loads Leo's ``FakeDog`` and Federico's ``FakeDrone`` by file path.
Real mode loads ``RealDog`` and ``RealDrone`` the same way. The three trees
each own a ``patrol`` package, so this module does not put ``dog backend`` or
the repo-root drone on ``sys.path``.

Real mode reads ``PATROL_DOG_HOST`` / ``PATROL_DOG_PORT`` and the drone pair.
A missing value fails closed and does not open a socket. A present value is
handed to the existing adapter. This module does not invent a host, a port,
or a key.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Event
from types import ModuleType
from typing import Any

from patrol.ground.kernel.paths import repo_root
from patrol.ground.museum.endpoint import (
    ConfigError,
    dog_real_config,
    drone_real_config,
    gap,
    require_endpoint,
)

__all__ = ["ConfigError", "DogPeer", "DronePeer", "open_dog", "open_drone"]


def _exec(name: str, path: Path, source: str | None = None) -> ModuleType:
    text = path.read_text(encoding="utf-8") if source is None else source
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(text, str(path), "exec"), module.__dict__)
    return module


def _load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _team_root() -> Path:
    return repo_root().parent


def load_fake_dog() -> type[Any]:
    """Return ``FakeDog`` without importing ``patrol.dog`` over Ground."""

    cached = sys.modules.get("museum_dog_fake")
    if cached is not None:
        return cached.FakeDog  # type: ignore[no-any-return]
    root = _team_root() / "dog backend"
    contract = root / "patrol" / "contract.py"
    fake = root / "patrol" / "dog" / "fake.py"
    if not contract.is_file() or not fake.is_file():
        raise ConfigError("dog backend fake is not in this checkout")
    _load_file("museum_dog_contract", contract)
    source = fake.read_text(encoding="utf-8").replace(
        "from patrol.contract import",
        "from museum_dog_contract import",
    )
    module = _exec("museum_dog_fake", fake, source)
    return module.FakeDog  # type: ignore[no-any-return]


def load_fake_drone() -> tuple[type[Any], Any, Any]:
    """Return ``(FakeDrone, InspectionRequest, RunContext)``."""

    cached = sys.modules.get("museum_drone_fake")
    if cached is not None:
        contract = sys.modules["museum_drone_contract"]
        return cached.FakeDrone, contract.InspectionRequest, contract.RunContext  # type: ignore[return-value]
    root = _team_root()
    contract_path = root / "patrol" / "contract.py"
    profile_path = root / "patrol" / "drone" / "profile.py"
    fake_path = root / "patrol" / "drone" / "fake.py"
    if not contract_path.is_file() or not fake_path.is_file():
        raise ConfigError("patrol/drone fake is not in this checkout")
    _load_file("museum_drone_contract", contract_path)
    profile_source = profile_path.read_text(encoding="utf-8").replace(
        "from patrol.contract import",
        "from museum_drone_contract import",
    )
    _exec("museum_drone_profile", profile_path, profile_source)
    fake_source = fake_path.read_text(encoding="utf-8")
    fake_source = fake_source.replace(
        "from patrol.contract import",
        "from museum_drone_contract import",
    )
    fake_source = fake_source.replace(
        "from patrol.drone.profile import allow",
        "from museum_drone_profile import allow",
    )
    module = _exec("museum_drone_fake", fake_path, fake_source)
    contract = sys.modules["museum_drone_contract"]
    return module.FakeDrone, contract.InspectionRequest, contract.RunContext  # type: ignore[return-value]


def load_real_dog() -> type[Any]:
    """Return ``RealDog`` without importing ``patrol.dog`` over Ground."""

    cached = sys.modules.get("museum_dog_real")
    if cached is not None:
        return cached.RealDog  # type: ignore[no-any-return]
    root = _team_root() / "dog backend"
    if "museum_dog_contract" not in sys.modules:
        contract = root / "patrol" / "contract.py"
        if not contract.is_file():
            raise ConfigError("dog backend real adapter is not in this checkout")
        _load_file("museum_dog_contract", contract)
    lidar = root / "patrol" / "dog" / "lidar.py"
    commands = root / "patrol" / "dog" / "commands.py"
    real = root / "patrol" / "dog" / "real.py"
    if not lidar.is_file() or not commands.is_file() or not real.is_file():
        raise ConfigError("dog backend real adapter is not in this checkout")
    if "museum_dog_lidar" not in sys.modules:
        _load_file("museum_dog_lidar", lidar)
    command_source = commands.read_text(encoding="utf-8").replace(
        "from patrol.contract import",
        "from museum_dog_contract import",
    )
    _exec("museum_dog_commands", commands, command_source)
    source = real.read_text(encoding="utf-8")
    source = source.replace("from patrol.contract import", "from museum_dog_contract import")
    source = source.replace(
        "from patrol.dog import lidar as lidar_mod",
        "import museum_dog_lidar as lidar_mod",
    )
    source = source.replace("from patrol.dog.commands import", "from museum_dog_commands import")
    source = source.replace(
        "from patrol.dog import audio as _audio",
        "import museum_dog_audio as _audio",
    )
    module = _exec("museum_dog_real", real, source)
    return module.RealDog  # type: ignore[no-any-return]


def load_real_drone() -> type[Any]:
    """Return ``RealDrone`` using the same isolated module names as the fake."""

    cached = sys.modules.get("museum_drone_real")
    if cached is not None:
        return cached.RealDrone  # type: ignore[no-any-return]
    load_fake_drone()
    root = _team_root()
    tello = root / "patrol" / "drone" / "tello_sdk.py"
    real = root / "patrol" / "drone" / "real.py"
    if not tello.is_file() or not real.is_file():
        raise ConfigError("patrol/drone real adapter is not in this checkout")
    if "museum_drone_tello_sdk" not in sys.modules:
        _load_file("museum_drone_tello_sdk", tello)
    source = real.read_text(encoding="utf-8")
    source = source.replace("from patrol.contract import", "from museum_drone_contract import")
    source = source.replace(
        "from patrol.drone.profile import allow",
        "from museum_drone_profile import allow",
    )
    source = source.replace(
        "from patrol.drone.tello_sdk import TelloSDK",
        "from museum_drone_tello_sdk import TelloSDK",
    )
    module = _exec("museum_drone_real", real, source)
    return module.RealDrone  # type: ignore[no-any-return]


class DogPeer:
    """Applies a Ground ``dog.command``. Anything else is ignored."""

    def __init__(self, dog: Any, *, real: bool = False) -> None:
        self.dog = dog
        self.real = real
        self.up = True
        self.ready = False
        self.halted = False
        self.effects: list[dict[str, object]] = []
        self.outcome = "ignored"
        self.last_gap: dict[str, object] | None = None
        self.endpoint_port: int | None = None
        self._extra_spoken: list[str] = []

    @property
    def spoken(self) -> list[str]:
        spoken = getattr(self.dog, "spoken", [])
        base = list(spoken) if isinstance(spoken, list) else []
        return base + [item for item in self._extra_spoken if item not in base]

    @property
    def trace(self) -> list[str]:
        trace = getattr(self.dog, "trace", [])
        return list(trace) if isinstance(trace, list) else []

    def link_ok(self) -> bool:
        if not self.up:
            return False
        alive = getattr(self.dog, "_link_alive", None)
        if callable(alive):
            try:
                return bool(alive())
            except Exception:
                return False
        connected = getattr(self.dog, "_connected", True)
        return bool(connected)

    async def connect(self, output_ready: bool = True) -> None:
        await self.dog.connect()
        if self.real:
            # RealDog.prepare stands the dog up. Follow and return_home are still
            # gaps, so the story does not stand it just to be ready.
            self.ready = True
            return
        if output_ready:
            ctx = _dog_context()
            await self.dog.prepare(ctx)
            await self.dog.capture_frame("room_2", ctx)
            self.ready = True

    def drop(self) -> None:
        self.up = False

    def _refuse(self, outcome: str) -> bool:
        self.outcome = outcome
        self.last_gap = None
        return False

    def _record_gap(self, action: str) -> bool:
        self.last_gap = gap(action)
        self.outcome = "gap"
        return False

    async def apply(self, command: Mapping[str, object]) -> bool:
        self.last_gap = None
        self.outcome = "ignored"
        if command.get("source") != "ground" or command.get("kind") != "dog.command":
            return False
        if command.get("destination") != "dog":
            return False
        payload = command.get("payload")
        if not isinstance(payload, Mapping):
            return False
        action = payload.get("action")
        if action not in {"play_warning", "follow", "stop", "return_home", "halt"}:
            return False
        if not isinstance(action, str):
            return False
        if not self.link_ok():
            if self.real and action == "halt":
                await self._halt()
                return True
            return self._refuse("down")
        if self.halted and action != "halt":
            return self._refuse("ignored")
        if action == "halt":
            await self._halt()
            return True
        if not self.ready:
            return self._refuse("ignored")
        if action == "play_warning":
            return await self._warn(payload)
        if action == "follow":
            return await self._follow(payload, command)
        if action == "stop":
            return await self._stop()
        if action == "return_home":
            return await self._return_home(command)
        return False

    async def _halt(self) -> None:
        await self.dog.halt()
        self.halted = True
        self.outcome = "applied"
        self.effects.append({"action": "halt"})

    async def _warn(self, payload: Mapping[str, object]) -> bool:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return self._refuse("ignored")
        if self.real:
            method = getattr(self.dog, "play_warning", None)
            warning_id = payload.get("warning_id")
            try:
                if method is not None:
                    await method(warning_id if isinstance(warning_id, str) else "", text)
                else:
                    await self.dog.say(text)
            except Exception as exc:
                if _adapter_gap(exc):
                    return self._record_gap("play_warning")
                raise
            spoken = getattr(self.dog, "spoken", None)
            if not (isinstance(spoken, list) and text in spoken):
                self._extra_spoken.append(text)
        else:
            await self.dog.say(text)
        self.outcome = "applied"
        self.effects.append({"action": "play_warning", "text": text})
        return True

    async def _follow(self, payload: Mapping[str, object], command: Mapping[str, object]) -> bool:
        standoff = payload.get("standoff_m")
        if isinstance(standoff, bool) or not isinstance(standoff, (int, float)):
            return self._refuse("ignored")
        if float(standoff) <= 0:
            return self._refuse("ignored")
        if self.real:
            try:
                await self.dog.execute(command)
            except Exception as exc:
                if _adapter_gap(exc):
                    return self._record_gap("follow")
                raise
        self.outcome = "applied"
        self.effects.append({"action": "follow", "standoff_m": float(standoff)})
        return True

    async def _stop(self) -> bool:
        if self.real:
            stop_move = getattr(self.dog, "stop_move", None)
            if stop_move is None:
                return self._record_gap("stop")
            await stop_move()
            self.effects.append({"action": "stop", "method": "stop_move"})
        else:
            self.effects.append({"action": "stop"})
        self.outcome = "applied"
        return True

    async def _return_home(self, command: Mapping[str, object]) -> bool:
        if self.real:
            try:
                await self.dog.execute(command)
            except Exception as exc:
                if _adapter_gap(exc):
                    return self._record_gap("return_home")
                raise
        self.outcome = "applied"
        self.effects.append({"action": "return_home"})
        return True


class DronePeer:
    """Applies a Ground ``drone.command``. Floor ``land()`` is not land-on-dog."""

    def __init__(self, drone: Any, *, real: bool = False) -> None:
        self.drone = drone
        self.real = real
        self.up = True
        self.effects: list[dict[str, object]] = []
        self.flight_state: str | None = None
        self.patrol_frame: str | None = None
        self.outcome = "ignored"
        self.last_gap: dict[str, object] | None = None
        self.endpoint_port: int | None = None

    @property
    def trace(self) -> list[str]:
        trace = getattr(self.drone, "trace", [])
        return list(trace) if isinstance(trace, list) else []

    def link_ok(self) -> bool:
        if not self.up:
            return False
        probe = getattr(self.drone, "link_ok", None)
        if callable(probe):
            try:
                return bool(probe())
            except Exception:
                return False
        return True

    async def patrol(self) -> None:
        await self.drone.connect()
        _fake_cls, request_cls, context_cls = load_fake_drone()
        ctx = context_cls(
            mission_id="demo-20261104-001",
            deadline_monotonic=time.monotonic() + 15.0,
            cancel=Event(),
        )
        result = await self.drone.inspect(
            request_cls(zone="room_2", profile_id="room_2_view_v1", launch_origin="floor"),
            ctx,
        )
        status = await self.drone.get_status()
        self.flight_state = str(getattr(status, "flight_state", "unknown"))
        frame = getattr(result, "frame", None)
        path = getattr(frame, "path", None)
        self.patrol_frame = path if isinstance(path, str) else None

    def drop(self) -> None:
        self.up = False

    async def apply(self, command: Mapping[str, object]) -> bool:
        self.last_gap = None
        self.outcome = "ignored"
        if command.get("source") != "ground" or command.get("kind") != "drone.command":
            return False
        if command.get("destination") != "drone":
            return False
        payload = command.get("payload")
        if not isinstance(payload, Mapping):
            return False
        action = payload.get("action")
        if action not in {"hover", "land_on_dog"}:
            return False
        if not self.link_ok():
            return self._refuse("down")
        if action == "land_on_dog":
            if self.real:
                # Do not call land(). The plate landing is a separate procedure.
                self.last_gap = gap("land_on_dog")
                self.outcome = "gap"
                return False
            self.effects.append({"action": "land_on_dog"})
            self.flight_state = "landed_on_dog"
            self.outcome = "applied"
            return True
        if self.real:
            hover = getattr(self.drone, "hover", None)
            if hover is not None:
                await hover()
        self.effects.append({"action": "hover"})
        self.outcome = "applied"
        return True

    def _refuse(self, outcome: str) -> bool:
        self.outcome = outcome
        self.last_gap = None
        return False

    async def halt(self) -> None:
        method = getattr(self.drone, "halt", None)
        if method is not None:
            await method()

    async def close(self) -> None:
        close = getattr(self.drone, "close", None)
        if close is not None:
            await close()


def _dog_context() -> Any:
    contract = sys.modules["museum_dog_contract"]
    return contract.RunContext(
        mission_id="demo-20261104-001",
        deadline_monotonic=time.monotonic() + 5.0,
        cancel=Event(),
    )


def _adapter_gap(exc: BaseException) -> bool:
    if isinstance(exc, ImportError):
        return True
    code = getattr(exc, "code", None)
    return code in {"unsupported", "invalid_input"}


def open_dog(
    mode: str,
    output_dir: Path,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
    *,
    conn_factory: Callable[[str], Any] | None = None,
) -> DogPeer:
    if mode == "real":
        host, port = require_endpoint("dog", environ, file_config)
        try:
            real = load_real_dog()
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(
                "dog real refused: adapter did not load "
                f"({type(exc).__name__}). No socket was opened."
            ) from exc
        dog = real(
            config=dog_real_config(host),
            output_dir=output_dir,
            _conn_factory=conn_factory,
        )
        peer = DogPeer(dog, real=True)
        peer.endpoint_port = port
        return peer
    if mode != "fake":
        raise ConfigError(f"dog mode {mode!r} is not fake or real")
    fake = load_fake_dog()
    dog = fake(config={"scenario": "blocked_resolved", "fake_route_s": 0.05}, output_dir=output_dir)
    return DogPeer(dog)


def open_drone(
    mode: str,
    output_dir: Path,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
    *,
    motion_authorized: bool = False,
    sdk_factory: Callable[[str, int], Any] | None = None,
    frame_source: Callable[[], bytes] | None = None,
    timing: Mapping[str, float] | None = None,
) -> DronePeer:
    if mode == "real":
        host, port = require_endpoint("drone", environ, file_config)
        try:
            real = load_real_drone()
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(
                "drone real refused: adapter did not load "
                f"({type(exc).__name__}). No socket was opened."
            ) from exc
        drone = real(
            config=drone_real_config(
                host,
                port,
                motion_authorized=motion_authorized,
                timing=timing,
            ),
            output_dir=output_dir,
            sdk_factory=sdk_factory,
            frame_source=frame_source,
        )
        peer = DronePeer(drone, real=True)
        peer.endpoint_port = port
        return peer
    if mode != "fake":
        raise ConfigError(f"drone mode {mode!r} is not fake or real")
    fake, _request, _context = load_fake_drone()
    drone = fake(config={"scenario": "blocked_resolved"}, output_dir=output_dir)
    return DronePeer(drone)
