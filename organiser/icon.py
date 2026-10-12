"""The app's icon, drawn in code so there is no image file to keep in sync.

Used for the tray icon at runtime and written out as ``.ico`` (Windows) or
``.icns`` (macOS) at build time.
Needs Pillow, which only the tray and the build use.
"""

from __future__ import annotations

FOLDER = (240, 180, 60)
FOLDER_DARK = (205, 140, 30)
SHEETS = ((70, 130, 220), (60, 170, 110), (225, 85, 85))


def make_image(size: int = 256):
    from PIL import Image, ImageDraw

    scale = 4  # draw large and shrink, for smooth edges at 16 px
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    u = s / 16

    # Folder back with its tab.
    draw.rounded_rectangle((1 * u, 3 * u, 7 * u, 6 * u), radius=u, fill=FOLDER_DARK)
    draw.rounded_rectangle((1 * u, 4 * u, 15 * u, 14 * u), radius=u, fill=FOLDER_DARK)
    # Three sorted sheets standing in the folder.
    for index, colour in enumerate(SHEETS):
        left = (3 + index * 3.5) * u
        draw.rounded_rectangle((left, 2.5 * u, left + 3 * u, 10 * u), radius=0.5 * u, fill=colour)
    # Folder front.
    draw.rounded_rectangle((1 * u, 7 * u, 15 * u, 14 * u), radius=u, fill=FOLDER)
    return image.resize((size, size), Image.LANCZOS)


def save_ico(path: str) -> None:
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    make_image(256).save(path, sizes=[(n, n) for n in sizes])


def save_icns(path: str) -> None:
    make_image(1024).save(path, format="ICNS")
