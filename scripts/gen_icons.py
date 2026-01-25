from pathlib import Path
from PIL import Image, ImageDraw
import math

root = Path(__file__).resolve().parent.parent / "src" / "parqcel" / "assets"
root.mkdir(parents=True, exist_ok=True)
svg = root / "parqcel_icon.svg"
png = root / "parqcel_icon.png"
ico = root / "parqcel_icon.ico"

# Canvas
img = Image.new("RGBA", (512, 512), (255, 255, 255, 0))
draw = ImageDraw.Draw(img)

# Base rounded rect
base_bounds = (16, 16, 496, 496)
draw.rounded_rectangle(base_bounds, radius=64, fill=(255, 255, 255, 255), outline="#1c2c46", width=24)

# Leaf block
leaf_bounds = (44, 44, 44 + 280, 44 + 260)
draw.rounded_rectangle(leaf_bounds, radius=24, fill="#66c89b", outline="#1c2c46", width=16)

# Leaf lines
line_color = "#3a9164"
lines = [
    ((84, 276), (84, 140), (324, 140)),
    ((84, 200), (200, 84)),
    ((160, 276), (324, 112)),
]
for coords in lines:
    draw.line(coords, fill=line_color, width=20, joint="curve")

# Diamond block via rotated layer
block = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
db = ImageDraw.Draw(block)
db.rounded_rectangle((10, 10, 190, 190), radius=20, fill="#7b6bce", outline="#1c2c46", width=16)
db.line((10, 100, 190, 100), fill="#1c2c46", width=16)
db.line((100, 10, 100, 190), fill="#1c2c46", width=16)
rot = block.rotate(20, expand=True, resample=Image.BICUBIC)
img.alpha_composite(rot, dest=(260, 230))

# Star highlight (simple 5-point star approximation)
star_center = (392, 110)
outer_r = 40
inner_r = 18
pts = []
for i in range(10):
    angle = math.radians(-90 + i * 36)
    r = outer_r if i % 2 == 0 else inner_r
    x = star_center[0] + r * math.cos(angle)
    y = star_center[1] + r * math.sin(angle)
    pts.append((x, y))
draw.polygon(pts, fill="#45c3d9")

img.save(png)
img.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
print(f"Wrote {png} and {ico}")
