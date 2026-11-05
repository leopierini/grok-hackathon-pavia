"""Jev's questions answered on the Mac, with no network.

The metric reflex already sees walls and furniture; what it misses is glass,
which it reads as the room behind. So the local brain splits the work:

- RT-DETRv2 (r18) finds people and their box, in about 35 ms.
- Qwen3-VL-2B answers one question per frame, "is the middle blocked by
  glass close to the camera". It never writes text: one forward pass, then
  the Yes/No token probabilities are read from the logits (about 300 ms).
- Steering comes from the reflex's side distances, in the navigator.

The photo stays whole. Cropping out the edges fixed the open door but also
threw away context, and it still blocked the one view whose door frame
reached the center. Telling the model to ignore the left and right edges
does both jobs: on the 4 Nov photos, at flight resolution, real glass reads
0.78 to 0.93 and an open door beside a clear floor reads at most 0.73, so
0.75 is the line. `blocked` is rescaled so that
line lands on the navigator's 0.5. Asked "is anything within 1.5 m", the same
model answered 0.5 to 0.7 on almost every photo and stopped on clear views.

The answers have the same shape as the OpenRouter client (`Guide`, `Scan`,
`Box`), so the explorer and the bench take either one.

    .venv/bin/python -m patrol.drone.local artifacts/drone/recon/<run>/step1-h090.jpg
"""

from __future__ import annotations

import base64
import io
import sys
import threading
import time
from pathlib import Path

from patrol.drone.jev import Box, Guide, JevError, Judgment, Scan

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
DETECTOR_DIR = MODELS / "rtdetr_v2_r18vd"
VLMS = {
    "qwen3-vl-2b": MODELS / "qwen3-vl-2b-instruct",
    "smolvlm-500m": MODELS / "smolvlm-500m-instruct",
}
DEFAULT_VLM = "qwen3-vl-2b"
VLM_SIZE = (448, 336)
PERSON_THRESHOLD = 0.3

GLASS = (
    "Ignore the left and right edges. Is the center of this photo blocked by glass"
    " or a transparent surface close to the camera? Answer Yes or No."
)
GLASS_LIMIT = 0.75
NO_LIMIT_M = 3.0


def decode(frame_b64: str):
    from PIL import Image

    return Image.open(io.BytesIO(base64.b64decode(frame_b64))).convert("RGB")


def rescale(glass: float, limit: float = GLASS_LIMIT) -> float:
    """Piecewise linear: 0 stays 0, `limit` becomes 0.5, 1 stays 1."""
    if glass <= limit:
        return 0.5 * glass / limit
    return 0.5 + 0.5 * (glass - limit) / (1 - limit)


def _device():
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


class Detector:
    """People and their boxes. Scores are the detector's own confidence."""

    def __init__(self, folder: Path = DETECTOR_DIR, device: str | None = None) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        if not folder.is_dir():
            raise FileNotFoundError(f"no detector at {folder}; run: hf download PekingU/rtdetr_v2_r18vd --local-dir {folder}")
        self.device = device or _device()
        self._torch = torch
        self.processor = AutoImageProcessor.from_pretrained(folder)
        self.model = AutoModelForObjectDetection.from_pretrained(folder).to(self.device).eval()
        names = {name.lower(): index for index, name in self.model.config.id2label.items()}
        self.person_id = int(names["person"])

    def people(self, image) -> list[tuple[float, tuple[float, float, float, float]]]:
        """(score, (left, top, right, bottom) as fractions of the frame), best first."""
        width, height = image.size
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with self._torch.inference_mode():
            outputs = self.model(**inputs)
        found = self.processor.post_process_object_detection(
            outputs, threshold=PERSON_THRESHOLD, target_sizes=[(height, width)]
        )[0]
        people = []
        for score, label, box in zip(found["scores"].tolist(), found["labels"].tolist(), found["boxes"].tolist()):
            if int(label) != self.person_id:
                continue
            left, top, right, bottom = box
            people.append((float(score), (left / width, top / height, right / width, bottom / height)))
        people.sort(key=lambda item: item[0], reverse=True)
        return people


class Judge:
    """A small vision-language model scored on its first answer token."""

    def __init__(self, name: str = DEFAULT_VLM, device: str | None = None) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        folder = VLMS.get(name)
        if folder is None:
            raise ValueError(f"vlm must be one of {', '.join(VLMS)}")
        if not folder.is_dir():
            raise FileNotFoundError(f"no model at {folder}")
        self.name = name
        self.device = device or _device()
        self._torch = torch
        dtype = torch.bfloat16 if self.device == "mps" else torch.float32
        self.processor = AutoProcessor.from_pretrained(folder)
        self.processor.tokenizer.padding_side = "left"
        if hasattr(self.processor.image_processor, "do_image_splitting"):
            self.processor.image_processor.do_image_splitting = False
        self.model = AutoModelForImageTextToText.from_pretrained(folder, dtype=dtype).to(self.device).eval()
        self._nested = self.model.config.model_type not in ("qwen2_vl", "qwen2_5_vl", "qwen3_vl")
        tokenizer = self.processor.tokenizer
        self._tokens = {word: self._ids(tokenizer, word) for word in ("Yes", "No", "A", "B", "C", "D")}

    @staticmethod
    def _ids(tokenizer, word: str) -> list[int]:
        ids = set()
        for variant in (word, " " + word, word.lower(), " " + word.lower()):
            encoded = tokenizer.encode(variant, add_special_tokens=False)
            if encoded:
                ids.add(encoded[0])
        return sorted(ids)

    def ask(self, items: list[tuple[object, str]], options: list[tuple[str, ...]]) -> list[list[float]]:
        """For each (image, question), the probability of each option word, summing to one."""
        torch = self._torch
        conversation = lambda question: [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": question}]}
        ]
        texts = [
            self.processor.apply_chat_template(conversation(question), add_generation_prompt=True)
            for _image, question in items
        ]
        images = [image.resize(VLM_SIZE) for image, _question in items]
        inputs = self.processor(
            text=texts,
            images=[[image] for image in images] if self._nested else images,
            padding=True,
            return_tensors="pt",
        ).to(self.device)
        with torch.inference_mode():
            logits = self.model(**inputs).logits[:, -1, :].float()
        answers = []
        for row, words in zip(logits, options):
            scores = torch.stack([torch.logsumexp(row[self._tokens[word]], dim=0) for word in words])
            answers.append(torch.softmax(scores, dim=0).tolist())
        return answers


class LocalBrain:
    """Drop-in for JevClient: guide, scan, box, close."""

    def __init__(self, vlm: str = DEFAULT_VLM, device: str | None = None, detector=None, judge=None) -> None:
        self.detector = detector or Detector(device=device)
        self.judge = judge or Judge(vlm, device=device)
        self.device = getattr(self.judge, "device", device)
        self._lock = threading.Lock()

    def guide(self, frame_b64: str, height_cm: int | None = None) -> Guide:
        """Steer is left to the reflex: confidence 0 means no opinion."""
        image = decode(frame_b64)
        with self._lock:
            started = time.monotonic()
            try:
                people = self.detector.people(image)
                (glass,) = self.judge.ask([(image, GLASS)], [("Yes", "No")])
            except Exception as exc:
                raise JevError(f"local guide failed: {exc}") from exc
            elapsed = time.monotonic() - started
        return Guide(
            blocked=rescale(glass[0]),
            steer="straight",
            steer_confidence=0.0,
            person=people[0][0] if people else 0.0,
            latency_s=elapsed,
        )

    def scan(self, frames: list[tuple[int, str]], back: int | None = None, height_cm: int | None = None) -> Scan:
        """Glass and people per photo. Room is the reflex's job, and the pick is choose_heading's."""
        images = [(heading, decode(b64)) for heading, b64 in frames]
        with self._lock:
            started = time.monotonic()
            try:
                answers = self.judge.ask([(image, GLASS) for _heading, image in images], [("Yes", "No")] * len(images))
                people = [self.detector.people(image) for _heading, image in images]
            except Exception as exc:
                print(f"local scan failed: {exc}; every direction reads blocked")
                return Scan({heading: Judgment(1.0, 0.0, 0.0) for heading, _b64 in frames}, None, 0.0)
            elapsed = time.monotonic() - started
        judgments = {
            heading: Judgment(
                blocked=rescale(answers[index][0]),
                room_m=NO_LIMIT_M,
                person=people[index][0][0] if people[index] else 0.0,
            )
            for index, (heading, _image) in enumerate(images)
        }
        return Scan(judgments, None, elapsed)

    def box(self, frame_b64: str) -> Box:
        image = decode(frame_b64)
        with self._lock:
            people = self.detector.people(image)
        if not people:
            raise JevError("no person in the frame")
        score, (left, top, right, bottom) = people[0]
        return Box(left=left, right=right, top=top, bottom=bottom, confidence=score, person=score)

    def close(self) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    import argparse

    from patrol.drone.jev import encode_frame
    from PIL import Image

    parser = argparse.ArgumentParser(description="Local Jev answers for photos")
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--vlm", default=DEFAULT_VLM, choices=sorted(VLMS))
    args = parser.parse_args(argv)
    started = time.monotonic()
    brain = LocalBrain(args.vlm)
    print(f"{args.vlm} + rtdetr on {brain.device}, loaded in {time.monotonic() - started:.1f} s")
    brain.guide(encode_frame(Image.open(args.photos[0])))
    for path in args.photos:
        guide = brain.guide(encode_frame(Image.open(path)))
        print(
            f"{path.name}  blocked {guide.blocked:.2f}  steer {guide.steer} ({guide.steer_confidence:.2f})"
            f"  person {guide.person:.2f}  {guide.latency_s * 1000:.0f} ms"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
