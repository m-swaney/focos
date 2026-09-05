"""Assemble app/favicon.ico from the PNG layers written by render-icons.mjs.

sharp has no .ico encoder, so this step is Python. Pillow's ICO writer is not usable here either:
it derives every size by resizing one source image and silently drops requested sizes larger than
that source, whereas this icon needs *different artwork* per size -- the zoomed "o" at 16px, where
the five-glyph wordmark collapses into a smear, and the full wordmark from 32px up. So the
container is written directly. 16/32/48 are stored as BMP/DIB and 256 as PNG, which is the layout
every browser and Explorer expects.

    node design/icons-focos/render-icons.mjs
    ..\\.venv\\Scripts\\python design/icons-focos/make-favicon.py
"""

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DASH = HERE.parent.parent
LAYERS = HERE / "favicon-layers"
SIZES = [16, 32, 48, 256]


def dib_payload(im: Image.Image) -> bytes:
    """A 32bpp BITMAPINFOHEADER image: bottom-up BGRA rows then a 1bpp AND mask."""
    w, h = im.size
    px = im.load()
    xor = bytearray()
    for y in range(h - 1, -1, -1):  # DIB rows run bottom-up
        for x in range(w):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))
    mask_row = ((w + 31) // 32) * 4  # 1bpp, each row padded to 4 bytes
    and_mask = bytes(mask_row * h)  # all zeros: every pixel opaque
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        w,  # biWidth
        h * 2,  # biHeight: XOR and AND masks stacked
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression = BI_RGB
        len(xor) + len(and_mask),  # biSizeImage
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor) + and_mask


payloads = []
for size in SIZES:
    src = LAYERS / f"{size}.png"
    if not src.exists():
        raise SystemExit(f"missing layer {src}; run render-icons.mjs first")
    im = Image.open(src).convert("RGBA")
    if im.size != (size, size):
        raise SystemExit(f"{src} is {im.size}, expected {(size, size)}")
    # 256 goes in as PNG; the small sizes as DIB. The PNG is re-encoded from the RGBA image rather
    # than copied from disk: Turbopack's ICO decoder rejects an embedded PNG without an alpha
    # channel, and the flattened layer from sharp is plain RGB.
    if size == 256:
        buf = BytesIO()
        im.save(buf, format="PNG", optimize=True)
        payloads.append(buf.getvalue())
    else:
        payloads.append(dib_payload(im))

offset = 6 + 16 * len(SIZES)
directory = b""
for size, payload in zip(SIZES, payloads):
    directory += struct.pack(
        "<BBBBHHII",
        size if size < 256 else 0,  # 0 means 256
        size if size < 256 else 0,
        0,  # no palette
        0,  # reserved
        1,  # colour planes
        32,  # bits per pixel
        len(payload),
        offset,
    )
    offset += len(payload)

out = DASH / "app" / "favicon.ico"
out.write_bytes(struct.pack("<HHH", 0, 1, len(SIZES)) + directory + b"".join(payloads))
print(f"{out.relative_to(DASH)}  {out.stat().st_size}b  sizes={SIZES}")
