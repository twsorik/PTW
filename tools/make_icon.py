"""Рисует иконку PTW (assets/ptw.ico и assets/ptw.png). Нужен Pillow."""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE = 512


def draw():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # вертикальный градиент в скруглённом квадрате
    grad = Image.new("RGBA", (SIZE, SIZE))
    gd = ImageDraw.Draw(grad)
    top, bottom = (92, 150, 255), (40, 70, 200)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        gd.line([(0, y), (SIZE, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([16, 16, SIZE - 16, SIZE - 16], radius=110, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # треугольник «play»
    cx, cy = SIZE // 2 + 18, 215
    d.polygon([(cx - 85, cy - 110), (cx - 85, cy + 110), (cx + 110, cy)], fill="white")
    # надпись PTW
    try:
        font = ImageFont.truetype("segoeuib.ttf", 120)
    except OSError:
        font = ImageFont.load_default()
    text = "PTW"
    w = d.textlength(text, font=font)
    d.text(((SIZE - w) / 2, 345), text, font=font, fill="white")
    return img


if __name__ == "__main__":
    img = draw()
    img.save(os.path.join(ROOT, "assets", "ptw.png"))
    img.save(os.path.join(ROOT, "assets", "ptw.ico"),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ok")
