"""Dog and drone seams for the museum story.

Fake mode loads Leo's ``FakeDog`` and Federico's ``FakeDrone`` by file path.
The three trees each own a ``patrol`` package, so this module does not put
``dog backend`` or the repo-root drone on ``sys.path``.

Real mode reads ``PATROL_DOG_HOST`` / ``PATROL_DOG_PORT`` and the drone pair.
A missing value fails closed. A present value still does not open a socket:
this offline entry point has no live transport.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from threading import Event
from types import ModuleType
from typing import Any

from patrol.ground.kernel.paths import repo_root


class ConfigError(Exception):
    """Closed configuration failure. The text must not contain a secret."""


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


def _blank(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def real_endpoint(
    peer: str,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
) -> None:
    """Fail closed. Does not open a socket and does not echo a host."""

    host_env = f"PATROL_{peer.upper()}_HOST"
    port_env = f"PATROL_{peer.upper()}_PORT"
    file_host: object = None
    file_port: object = None
    if isinstance(file_config, Mapping):
        section = file_config.get(peer)
        if isinstance(section, Mapping):
            file_host = section.get("host")
            file_port = section.get("port")
    host = _blank(environ.get(host_env)) or _blank(file_host)
    port = _blank(environ.get(port_env)) or _blank(file_port)
    missing = [name for name, value in ((host_env, host), (port_env, port)) if value is None]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(
            f"{peer} real refused: {joined} unset. No socket was opened. "
            "Set the variables in the environment, or pass --config with those "
            "values filled in. The example file leaves them null on purpose."
        )
    raise ConfigError(
        f"{peer} real refused: {host_env} and {port_env} are set, but this offline "
        "entry point does not open a socket. No motion was sent. "
        "See docs/HARDWARE_BRINGUP.md."
    )


class DogPeer:
    """Applies a Ground ``dog.command``. Anything else is ignored."""

    def __init__(self, dog: Any) -> None:
        self.dog = dog
        self.up = True
        self.ready = False
        self.halted = False
        self.effects: list[dict[str, object]] = []

    @property
    def spoken(self) -> list[str]:
        spoken = getattr(self.dog, "spoken", [])
        return list(spoken) if isinstance(spoken, list) else []

    @property
    def trace(self) -> list[str]:
        trace = getattr(self.dog, "trace", [])
        return list(trace) if isinstance(trace, list) else []

    async def connect(self, output_ready: bool = True) -> None:
        await self.dog.connect()
        if output_ready:
            ctx = _dog_context()
            await self.dog.prepare(ctx)
            await self.dog.capture_frame("room_2", ctx)
            self.ready = True

    def drop(self) -> None:
        self.up = False

    async def apply(self, command: Mapping[str, object]) -> bool:
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
        if not self.up:
            return False
        if self.halted and action != "halt":
            return False
        if action == "halt":
            await self.dog.halt()
            self.halted = True
            self.effects.append({"action": "halt"})
            return True
        if not self.ready:
            return False
        if action == "play_warning":
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                return False
            await self.dog.say(text)
            self.effects.append({"action": "play_warning", "text": text})
            return True
        if action == "follow":
            standoff = payload.get("standoff_m")
            if isinstance(standoff, bool) or not isinstance(standoff, (int, float)):
                return False
            if float(standoff) <= 0:
                return False
            self.effects.append({"action": "follow", "standoff_m": float(standoff)})
            return True
        if action in {"stop", "return_home"}:
            self.effects.append({"action": action})
            return True
        return False


class DronePeer:
    """Applies a Ground ``drone.command``. Floor ``land()`` is not land-on-dog."""

    def __init__(self, drone: Any) -> None:
        self.drone = drone
        self.up = True
        self.effects: list[dict[str, object]] = []
        self.flight_state: str | None = None
        self.patrol_frame: str | None = None

    @property
    def trace(self) -> list[str]:
        trace = getattr(self.drone, "trace", [])
        return list(trace) if isinstance(trace, list) else []

    async def patrol(self) -> None:
        await self.drone.connect()
        fake_cls, request_cls, context_cls = load_fake_drone()
        del fake_cls
        ctx = context_cls(
            mission_id="demo-20261104-001",
            deadline_monotonic=time.monotonic() + 5.0,
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
        if not self.up:
            return False
        if action == "land_on_dog":
            # Federico's fake lands on the floor inside inspect. Do not call it again.
            self.effects.append({"action": "land_on_dog"})
            self.flight_state = "landed_on_dog"
            return True
        self.effects.append({"action": "hover"})
        return True

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


def open_dog(
    mode: str,
    output_dir: Path,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
) -> DogPeer:
    if mode == "real":
        real_endpoint("dog", environ, file_config)
        raise ConfigError("dog real refused: no socket was opened")
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
) -> DronePeer:
    if mode == "real":
        real_endpoint("drone", environ, file_config)
        raise ConfigError("drone real refused: no socket was opened")
    if mode != "fake":
        raise ConfigError(f"drone mode {mode!r} is not fake or real")
    fake, _request, _context = load_fake_drone()
    drone = fake(config={"scenario": "blocked_resolved"}, output_dir=output_dir)
    return DronePeer(drone)
