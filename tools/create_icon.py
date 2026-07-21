"""Create a simple PNG tray icon without external deps."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, size: int = 64) -> None:
    rows = []
    cx = cy = (size - 1) / 2
    r_outer = size * 0.38
    for y in range(size):
        row = bytearray([0])  # filter none
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= r_outer:
                # dial face
                row.extend((28, 36, 43, 255))
            elif abs(dist - r_outer) < 1.2:
                row.extend((243, 245, 247, 255))
            else:
                row.extend((0, 0, 0, 0))
        # hands
        rows.append(bytes(row))

    # redraw with hands on top via second pass into pixel buffer
    pixels = [bytearray(row) for row in rows]
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            # hour hand (vertical-ish)
            if abs(dx) <= 1.5 and 0 <= -dy <= r_outer * 0.55 and dist <= r_outer:
                i = 1 + x * 4
                pixels[y][i : i + 4] = bytearray((243, 245, 247, 255))
            # minute hand
            if abs(dy) <= 1.5 and 0 <= dx <= r_outer * 0.7 and dist <= r_outer:
                i = 1 + x * 4
                pixels[y][i : i + 4] = bytearray((200, 210, 220, 255))
            # center
            if dist <= 2.5:
                i = 1 + x * 4
                pixels[y][i : i + 4] = bytearray((243, 245, 247, 255))

    raw = b"".join(bytes(row) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "resources" / "icon.png"
    write_png(target)
    print(f"Wrote {target}")
