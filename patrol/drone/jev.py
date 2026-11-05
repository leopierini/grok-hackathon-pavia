"""Jev, TypeSafe's decision model, reached through OpenRouter.

Jev answers typed questions about photos: a probability for a yes/no
statement (noul), one option from a list (choice), a level on a scale
(score), or where something is in an image (box). It never writes prose,
so the answers drive the drone directly.

Two calls matter in flight. `guide` reads the newest front frame: is
something close ahead, which way to steer, is a person in sight. `scan`
reads the four frames of a turn in place and picks where to go. A call
that fails or times out reads as blocked, never as clear.

The key is OPENROUTER_API_KEY, from the environment or the repo `.env`.

    .venv/bin/python -m patrol.drone.jev artifacts/drone/recon/<run>/step1-h090.jpg
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import math
import os
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

HOST = "openrouter.ai"
PATH = "/api/alpha/decisions"
MODEL = "typesafe/jev-1.14"
ROOT = Path(__file__).resolve().parents[2]
FRAME_SIZE = (640, 480)
JPEG_QUALITY = 80
TIMEOUT_S = 4.0
BLOCKED_AHEAD = (
    "Something solid (a wall, pillar, door, shelf, furniture, vehicle, or person) is less than "
    "about 1.5 meters straight ahead in the middle of {photo}, at the camera's height, so a small "
    "drone flying straight forward would hit it."
)
PERSON = "A person is visible in {photo}."
STEER = {
    "left": "The way ahead is more open to the left of the middle of {photo}.",
    "straight": "The middle of {photo} is the most open way ahead.",
    "right": "The way ahead is more open to the right of the middle of {photo}.",
}
ROOM = (
    ("less than half a meter", 0.3),
    ("about one meter", 1.0),
    ("about two meters", 2.0),
    ("three meters or more", 3.0),
)


class JevError(RuntimeError):
    """No usable answer. The caller treats this as blocked."""


@dataclass(frozen=True)
class Guide:
    blocked: float
    steer: str
    steer_confidence: float
    person: float
    latency_s: float


@dataclass(frozen=True)
class Judgment:
    blocked: float
    room_m: float
    person: float


@dataclass(frozen=True)
class Scan:
    judgments: dict[int, Judgment]
    choice: int | None
    latency_s: float


@dataclass(frozen=True)
class Box:
    left: float
    right: float
    top: float
    bottom: float
    confidence: float
    person: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2


def api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    env = ROOT / ".env"
    if not env.is_file():
        return None
    for line in env.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY" and value.strip():
            return value.strip().strip("'\"")
    return None


def encode_frame(image) -> str:
    """JPEG at 640x480, base64. Smaller uploads answer sooner; Jev needs at least 256 px a side."""
    small = image.convert("RGB").resize(FRAME_SIZE)
    buffer = io.BytesIO()
    small.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode()


def _image(b64: str) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}


def _label(heading: int) -> str:
    return f"h{int(heading) % 360:03d}"


def guide_request(frame_b64: str, height_cm: int | None) -> dict:
    at = "" if height_cm is None else f" at about {int(height_cm)} cm above the floor"
    photo = "the front camera photo"
    return {
        "model": MODEL,
        "state": [
            f"Front camera of a small indoor patrol drone{at}, looking where it flies.",
            _image(frame_b64),
        ],
        "questions": {
            "blocked": {"type": "noul", "instructions": BLOCKED_AHEAD.format(photo=photo)},
            "steer": {
                "type": "choice",
                "instructions": f"Which way should the drone steer to stay clear of obstacles in {photo}?",
                "criteria": {name: text.format(photo=photo) for name, text in STEER.items()},
            },
            "person": {"type": "noul", "instructions": PERSON.format(photo=photo)},
        },
    }


def scan_request(frames: list[tuple[int, str]], back: int | None, height_cm: int | None) -> dict:
    """One call for a turn in place. Headings are absolute degrees, clockwise.

    `back` is the heading of the photo that looks the way the drone came.
    """
    at = "" if height_cm is None else f" at about {int(height_cm)} cm above the floor"
    state: list = [
        f"A small indoor patrol drone{at} turned in place and took one front photo per direction. "
        "Each photo follows its label. It explores open floor space and must not fly into anything."
    ]
    if back is not None:
        state.append(f"Photo {_label(back)} looks back the way the drone came.")
    questions: dict = {}
    criteria: dict = {}
    for heading, b64 in frames:
        label = _label(heading)
        photo = f"the photo labelled {label}"
        state.extend([f"Photo {label}:", _image(b64)])
        questions[f"blocked_{label}"] = {"type": "noul", "instructions": BLOCKED_AHEAD.format(photo=photo)}
        questions[f"room_{label}"] = {
            "type": "score",
            "instructions": (
                f"How far a small drone could fly straight ahead through the middle of {photo}, "
                "at the camera's height, before reaching anything solid."
            ),
            "criteria": [text for text, _m in ROOM],
        }
        questions[f"person_{label}"] = {"type": "noul", "instructions": PERSON.format(photo=photo)}
        criteria[label] = f"Fly toward {photo}."
    criteria["stay"] = "Every direction is blocked or unsafe."
    questions["heading"] = {
        "type": "choice",
        "instructions": (
            "Which way should the drone fly next to explore safely: open space, not toward walls, "
            "people at close range, or obstacles, and preferably not back where it came from?"
        ),
        "criteria": criteria,
    }
    return {"model": MODEL, "state": state, "questions": questions}


def box_request(frame_b64: str) -> dict:
    return {
        "model": MODEL,
        "state": ["Front camera photo of a small indoor patrol drone:", _image(frame_b64)],
        "questions": {
            "person": {"type": "noul", "instructions": "A person is visible in the front camera photo."},
            "where": {"type": "box", "instructions": "the person nearest the camera in the front camera photo"},
        },
    }


def _answer(answers: dict, name: str, kind: str) -> dict:
    found = answers.get(name)
    if not isinstance(found, dict) or found.get("type") != kind:
        raise JevError(f"answer {name} missing or not a {kind}")
    return found


def _probability(answers: dict, name: str) -> float:
    value = _answer(answers, name, "noul").get("noul")
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise JevError(f"answer {name} has no probability")
    return float(value)


def room_meters(score: float) -> float:
    """The level at or below the score: a 1.7 between one and two meters reads as one meter."""
    index = max(0, min(len(ROOM) - 1, int(math.floor(score))))
    return ROOM[index][1]


def parse_guide(answers: dict, latency_s: float) -> Guide:
    steer = _answer(answers, "steer", "choice")
    choice = steer.get("choice")
    if choice not in STEER:
        raise JevError("steer is not left, straight, or right")
    confidence = steer.get("confidence")
    return Guide(
        blocked=_probability(answers, "blocked"),
        steer=choice,
        steer_confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.0,
        person=_probability(answers, "person"),
        latency_s=latency_s,
    )


def parse_scan(answers: dict, headings: list[int], latency_s: float) -> Scan:
    judgments = {}
    for heading in headings:
        label = _label(heading)
        score = _answer(answers, f"room_{label}", "score").get("score")
        if not isinstance(score, (int, float)):
            raise JevError(f"room_{label} has no score")
        judgments[heading] = Judgment(
            blocked=_probability(answers, f"blocked_{label}"),
            room_m=room_meters(float(score)),
            person=_probability(answers, f"person_{label}"),
        )
    picked = _answer(answers, "heading", "choice").get("choice")
    by_label = {_label(heading): heading for heading in headings}
    if picked != "stay" and picked not in by_label:
        raise JevError("heading is not one of the photos")
    return Scan(judgments=judgments, choice=by_label.get(picked), latency_s=latency_s)


def blocked_scan(headings: list[int]) -> Scan:
    """What a failed scan call means: nothing is known to be clear."""
    return Scan({heading: Judgment(1.0, 0.0, 0.0) for heading in headings}, None, 0.0)


def parse_box(answers: dict) -> Box:
    where = _answer(answers, "where", "box")
    edges = where.get("box")
    if not isinstance(edges, dict) or not all(isinstance(edges.get(k), (int, float)) for k in ("left", "right", "top", "bottom")):
        raise JevError("box has no edges")
    confidence = where.get("confidence")
    return Box(
        left=float(edges["left"]),
        right=float(edges["right"]),
        top=float(edges["top"]),
        bottom=float(edges["bottom"]),
        confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.0,
        person=_probability(answers, "person"),
    )


class JevClient:
    """One kept-alive HTTPS connection. A warm connection answers in about 250 to 580 ms."""

    def __init__(self, key: str, timeout_s: float = TIMEOUT_S, connection_factory=None) -> None:
        self._key = key
        self._timeout = timeout_s
        self._factory = connection_factory or (
            lambda: http.client.HTTPSConnection(HOST, timeout=timeout_s, context=ssl.create_default_context())
        )
        self._conn = None
        self._lock = threading.Lock()

    def ask(self, body: dict) -> tuple[dict, float]:
        """Answers and seconds taken. Raises JevError on anything but a clean answer."""
        payload = json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        }
        with self._lock:
            started = time.monotonic()
            for attempt in (0, 1):
                if self._conn is None:
                    self._conn = self._factory()
                try:
                    self._conn.request("POST", PATH, body=payload, headers=headers)
                    response = self._conn.getresponse()
                    raw = response.read()
                    status = response.status
                    break
                except (http.client.HTTPException, OSError, socket.timeout) as exc:
                    self._drop()
                    if attempt == 1 or time.monotonic() - started > self._timeout:
                        raise JevError(f"no reply: {exc}") from exc
            elapsed = time.monotonic() - started
        if status != 200:
            raise JevError(f"http {status}: {raw[:200].decode(errors='replace')}")
        try:
            answers = json.loads(raw)["answers"]
        except (ValueError, KeyError, TypeError) as exc:
            raise JevError("reply has no answers") from exc
        if not isinstance(answers, dict):
            raise JevError("reply has no answers")
        return answers, elapsed

    def guide(self, frame_b64: str, height_cm: int | None = None) -> Guide:
        answers, elapsed = self.ask(guide_request(frame_b64, height_cm))
        return parse_guide(answers, elapsed)

    def scan(self, frames: list[tuple[int, str]], back: int | None = None, height_cm: int | None = None) -> Scan:
        headings = [heading for heading, _b64 in frames]
        try:
            answers, elapsed = self.ask(scan_request(frames, back, height_cm))
            return parse_scan(answers, headings, elapsed)
        except JevError as exc:
            print(f"jev scan failed: {exc}; every direction reads blocked")
            return blocked_scan(headings)

    def box(self, frame_b64: str) -> Box:
        answers, _elapsed = self.ask(box_request(frame_b64))
        return parse_box(answers)

    def _drop(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def close(self) -> None:
        with self._lock:
            self._drop()


def main(argv: list[str] | None = None) -> int:
    from PIL import Image

    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print("give one or more photo paths")
        return 2
    key = api_key()
    if not key:
        print("set OPENROUTER_API_KEY in the environment or in .env")
        return 1
    client = JevClient(key)
    try:
        for path in paths:
            guide = client.guide(encode_frame(Image.open(path)))
            print(
                f"{path.name}  blocked {guide.blocked:.2f}  steer {guide.steer} ({guide.steer_confidence:.2f})"
                f"  person {guide.person:.2f}  {guide.latency_s * 1000:.0f} ms"
            )
    except JevError as exc:
        print(f"jev failed: {exc}")
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
