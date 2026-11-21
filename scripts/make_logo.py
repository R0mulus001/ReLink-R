"""ReLink-R's icon and logo, drawn from one sword (the 0.0.3-dev drafts): launcher/app.ico (the launcher and the game, through
nx2/make_icon.py), launcher/setup/relink.ico (ReLinkR-Setup.exe) and assets/relink.png (the logo the game folder gets).

The violet square with round corners, the sword standing in it. The grip is dark on the violet, so the hilt reads as one piece
from the guard to the pommel at every size; the blade, the grip and the guard each start a little under the part drawn over
them, so no seam of the violet shows between them. The small frames (32 pixels and under) draw the sword wider and taller,
without its fuller, so that it is still a sword at 16 pixels.

Needs rsvg-convert (librsvg) and Pillow. Run from anywhere: python scripts/make_logo.py
"""
import io
import os
import struct
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sword(small):
    """The sword in its own 80 x 260 box, blade up"""
    fuller = "" if small else '<rect x="38.75" y="30" width="2.5" height="130" rx="1.25" fill="#8C98C6"/>'
    wraps = "".join(f'<rect x="33" y="{y}" width="14" height="{5 if small else 3}" fill="#7A6AF0"/>' for y in (192, 204, 216))
    return f"""
      <polygon points="40,4 49,26 49,173 31,173 31,26" fill="#C9D3EE"/>
      <polygon points="40,4 49,26 49,173 40,173" fill="#EEF2FF"/>
      {fuller}
      <rect x="33" y="178" width="14" height="54" rx="4" fill="#2A2170"/>
      {wraps}
      <rect x="10" y="170" width="60" height="12" rx="6" fill="#E2BE5A"/>
      <circle cx="11" cy="176" r="7" fill="#E2BE5A"/>
      <circle cx="69" cy="176" r="7" fill="#E2BE5A"/>
      <circle cx="40" cy="176" r="8" fill="#2A2170" stroke="#F6E3A6" stroke-width="{3.5 if small else 2.5}"/>
      <circle cx="40" cy="239" r="11" fill="#E2BE5A"/>
      <circle cx="40" cy="239" r="{5.5 if small else 4.5}" fill="#2A2170"/>"""


def svg(size):
    small = size <= 32
    tall = 0.86 if small else 0.78        # (the sword's height, a share of the square)
    wide = 1.45 if small else 1.0         # (how much wider than drawn: the small frames)
    s = size * tall / 260
    left = size / 2 - 40 * s * wide
    top = (size - 254 * s) / 2 - 0.5 * s
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs><linearGradient id="g" x1="0.2" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="#7A6AF0"/><stop offset="1" stop-color="#4B3CC4"/></linearGradient></defs>
  <rect width="{size}" height="{size}" rx="{size * 0.25:.2f}" fill="url(#g)"/>
  <g transform="translate({left:.3f} {top:.3f}) scale({s * wide:.5f} {s:.5f})">{sword(small)}
  </g>
</svg>"""


def render(size):
    png = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size)], input=svg(size).encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def png_bytes(im):
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def write_ico(path, sizes):
    """An .ico whose frames are PNG, one drawn for each size"""
    frames = [(size, png_bytes(render(size))) for size in sizes]
    head = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, data = b"", b""
    for size, blob in frames:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    with open(path, "wb") as f:
        f.write(head + entries + data)
    print(path, sizes)


def main():
    write_ico(os.path.join(ROOT, "launcher", "app.ico"), [16, 24, 32, 48, 64, 128, 256])
    write_ico(os.path.join(ROOT, "launcher", "setup", "relink.ico"), [16, 24, 32, 48, 64, 256])
    logo = os.path.join(ROOT, "assets", "relink.png")
    render(512).save(logo, "PNG", optimize=True)
    print(logo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
