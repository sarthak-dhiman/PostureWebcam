"""
convert_icon_macos.py
Converts office.png to office.icns for macOS PyInstaller builds.
Safe to run on any OS; exits 0 silently if input is missing or conversion fails.
"""
import sys
from pathlib import Path

png = Path("office.png")
if not png.exists():
    print("office.png not found — skipping icon conversion")
    sys.exit(0)

try:
    from PIL import Image
    img = Image.open(png).convert("RGBA")
    sizes = [(16, 16), (32, 32), (64, 64), (128, 128),
             (256, 256), (512, 512), (1024, 1024)]
    imgs = [img.resize(s, Image.LANCZOS) for s in sizes]
    imgs[0].save("office.icns", format="ICNS", append_images=imgs[1:])
    print("office.icns written")
except Exception as e:
    print(f"Icon conversion failed ({e}) — skipping")
