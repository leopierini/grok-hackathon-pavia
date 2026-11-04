"""Small JPEG fixture writer. Production validation never calls this."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def jpeg_bytes(
    *, size: tuple[int, int] = (8, 8), color: tuple[int, int, int] = (20, 40, 60)
) -> bytes:
    from PIL import Image

    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def write_jpeg(
    path: Path,
    *,
    size: tuple[int, int] = (8, 8),
    color: tuple[int, int, int] = (20, 40, 60),
) -> bytes:
    data = jpeg_bytes(size=size, color=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def materialize_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    phone = write_jpeg(root / "phone.jpg", color=(10, 20, 30))
    write_jpeg(root / "dog.jpg", color=(30, 10, 10))
    write_jpeg(root / "drone.jpg", color=(10, 10, 30))
    (root / "empty.jpg").write_bytes(b"")
    (root / "truncated.jpg").write_bytes(phone[: max(2, len(phone) // 2)])
    (root / "not_jpeg.jpg").write_bytes(b"this is not a jpeg\n")


if __name__ == "__main__":
    materialize_fixtures(Path(__file__).resolve().parents[4] / "fixtures" / "ground" / "g06")
