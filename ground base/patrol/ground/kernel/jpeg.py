"""Tiny readable JPEG bytes. The image is a fixture, not a camera frame."""

from __future__ import annotations

import io


def tiny_jpeg_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (18, 64, 96)).save(buffer, format="JPEG")
    return buffer.getvalue()
