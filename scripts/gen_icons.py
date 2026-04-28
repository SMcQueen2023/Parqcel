from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

root = Path(__file__).resolve().parent.parent / "src" / "parqcel" / "assets"
root.mkdir(parents=True, exist_ok=True)
svg = root / "parqcel_icon.svg"
png = root / "parqcel_icon.png"
ico = root / "parqcel_icon.ico"

SIZE = 512


def blend(color_a, color_b, ratio):
    return tuple(
        int(color_a[i] * (1 - ratio) + color_b[i] * ratio) for i in range(4)
    )


def gradient_fill(size, start_color, end_color, diagonal=False):
    width, height = size
    img = Image.new("RGBA", size)
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            if diagonal:
                ratio = ((x / max(width - 1, 1)) + (y / max(height - 1, 1))) / 2
            else:
                ratio = y / max(height - 1, 1)
            pixels[x, y] = blend(start_color, end_color, ratio)
    return img


def rounded_mask(size, bounds, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=radius, fill=255)
    return mask


def paste_gradient(target, bounds, radius, start_color, end_color, diagonal=False):
    x0, y0, x1, y1 = bounds
    layer = gradient_fill((x1 - x0, y1 - y0), start_color, end_color, diagonal)
    mask = rounded_mask((x1 - x0, y1 - y0), (0, 0, x1 - x0, y1 - y0), radius)
    target.paste(layer, (x0, y0), mask)


def add_shadow(target, bounds, radius, offset, blur, alpha):
    shadow = Image.new("RGBA", target.size, (0, 0, 0, 0))
    sx0, sy0, sx1, sy1 = bounds
    ImageDraw.Draw(shadow).rounded_rectangle(
        (sx0 + offset[0], sy0 + offset[1], sx1 + offset[0], sy1 + offset[1]),
        radius=radius,
        fill=(0, 0, 0, alpha),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    target.alpha_composite(shadow)


img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

add_shadow(img, (22, 18, 490, 490), 96, (0, 20), 22, 110)
paste_gradient(
    img,
    (18, 14, 494, 490),
    96,
    (7, 20, 52, 255),
    (21, 58, 116, 255),
    diagonal=True,
)
draw.rounded_rectangle((18, 14, 494, 490), radius=96, outline="#254e8e", width=2)

tile_w = 72
tile_h = 56
tile_x = 108
tile_y = 108
for row in range(5):
    for col in range(2):
        x0 = tile_x + col * tile_w
        y0 = tile_y + row * tile_h
        x1 = x0 + tile_w - 2
        y1 = y0 + tile_h - 2
        start = (82 - row * 4, 198 - row * 8, 255 - row * 6, 255)
        end = (20, 74 + row * 8, 198 + row * 6, 255)
        paste_gradient(img, (x0, y0, x1, y1), 6, start, end, diagonal=True)

for offset, color in [((0, 66), (15, 194, 226, 210)), ((0, 42), (16, 120, 245, 210)), ((0, 18), (18, 76, 235, 215))]:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.rounded_rectangle(
        (108 + offset[0], 334 + offset[1], 248 + offset[0], 392 + offset[1]),
        radius=18,
        fill=color,
    )
    layer = layer.filter(ImageFilter.GaussianBlur(4))
    img.alpha_composite(layer)

arch_mask = Image.new("L", img.size, 0)
arch_draw = ImageDraw.Draw(arch_mask)
arch_draw.rounded_rectangle((108, 72, 444, 318), radius=116, fill=255)
arch_draw.rounded_rectangle((255, 126, 366, 240), radius=54, fill=0)
arch_draw.rectangle((108, 182, 256, 318), fill=0)
arch_gradient = gradient_fill(img.size, (90, 202, 255, 255), (108, 255, 210, 255), diagonal=True)
arch_shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
ImageDraw.Draw(arch_shadow).rounded_rectangle((116, 84, 452, 330), radius=116, fill=(0, 0, 0, 80))
arch_shadow = arch_shadow.filter(ImageFilter.GaussianBlur(14))
img.alpha_composite(arch_shadow)
img.paste(arch_gradient, (0, 0), arch_mask)

ribbon_layers = [
    (20, (10, 178, 212, 255)),
    (10, (20, 208, 228, 255)),
    (0, (24, 219, 195, 255)),
]
ribbon_points = [(108, 390), (156, 352), (208, 326), (266, 302), (318, 274), (382, 236), (392, 246), (326, 290), (274, 330), (242, 380), (120, 390)]
for offset_y, color in ribbon_layers:
    ribbon = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ribbon_draw = ImageDraw.Draw(ribbon)
    ribbon_draw.polygon([(x, y + offset_y) for x, y in ribbon_points], fill=color)
    ribbon = ribbon.filter(ImageFilter.GaussianBlur(3))
    img.alpha_composite(ribbon)

curve_points = [(214, 325), (260, 305), (306, 283), (356, 252), (390, 226)]
draw.line(curve_points, fill="#baf6e7", width=6, joint="curve")
for cx, cy in [(214, 325), (304, 266), (388, 226)]:
    draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill="#e6fff8")

img.save(png)
img.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
print(f"Wrote {png} and {ico}")
