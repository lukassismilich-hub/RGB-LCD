# ikona_vytvorit.py - vygeneruje ikona.ico (ikona okna nastaveni a zastupce na plose)
# Spusteni: py ikona_vytvorit.py   (nahled vsech velikosti: %TEMP%\ikona_nahled.png)
import math
import os
import sys

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from screens import mix  # noqa: E402  stejny prechod pres odstin jako na LCD

HERE = os.environ.get("TEMP", BASE)   # kam ulozit nahled PNG
N = 1024                      # kresli se velke, pak se zmensuje
C = N / 2


def arc_ring(img, r_out, width, start, span, c1, c2, c3):
    """Oblouk s prechodem c1 -> c2 -> c3 a zakulacenymi konci."""
    d = ImageDraw.Draw(img)
    r = r_out - width / 2
    box = (C - r_out, C - r_out, C + r_out, C + r_out)
    steps = int(span * 4)
    for i in range(steps):
        t = i / (steps - 1)
        col = mix(c1, c2, t * 2) if t < 0.5 else mix(c2, c3, (t - 0.5) * 2)
        a0 = start + span * i / steps
        d.arc(box, a0, a0 + span / steps + 0.6, fill=col, width=int(width))
    for ang, col in ((start, c1), (start + span, c3)):
        a = math.radians(ang)
        x, y = C + r * math.cos(a), C + r * math.sin(a)
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=col)


def gear(img, r_body, r_tip, teeth, r_hole, col):
    d = ImageDraw.Draw(img)
    pts = []
    for i in range(teeth * 4):
        # zub: dve spicky nahore, dve dole (lichobeznik)
        a = 2 * math.pi * i / (teeth * 4) - math.pi / 2
        rr = r_tip if i % 4 in (1, 2) else r_body
        pts.append((C + rr * math.cos(a), C + rr * math.sin(a)))
    d.polygon(pts, fill=col)
    d.ellipse((C - r_body, C - r_body, C + r_body, C + r_body), fill=col)
    d.ellipse((C - r_hole, C - r_hole, C + r_hole, C + r_hole), fill=(16, 18, 23, 255))   # otvor v barve disku


def make(small=False):
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # telo: tmavy disk s jemnym svetlejsim okrajem (jako hlava pumpy s displejem)
    d.ellipse((24, 24, N - 24, N - 24), fill=(58, 62, 72, 255))
    d.ellipse((48, 48, N - 48, N - 48), fill=(16, 18, 23, 255))
    # oblouk - u malych velikosti silnejsi, aby byl citelny
    w = 150 if small else 112
    arc_ring(img, N / 2 - 92, w, 135, 270, (60, 220, 40), (240, 220, 20), (255, 40, 30))
    # ozubene kolo uprostred
    if small:
        gear(img, 190, 250, 8, 80, (245, 245, 245, 255))
    else:
        gear(img, 160, 215, 8, 70, (245, 245, 245, 255))
    return img


def main():
    big, small = make(False), make(True)
    sizes = [256, 128, 64, 48, 32, 24, 16]
    frames = []
    for s in sizes:
        src = small if s <= 32 else big
        frames.append(src.resize((s, s), Image.LANCZOS))
    out = os.path.join(BASE, "ikona.ico")
    frames[0].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[1:])
    # nahled: vsechny velikosti vedle sebe na svetlem i tmavem pozadi
    W = sum(sizes) + 20 * len(sizes) + 20
    prev = Image.new("RGB", (W, 2 * 276 + 20), (240, 240, 240))
    prev.paste((32, 32, 32), (0, 296, W, 2 * 276 + 20))
    x = 20
    for f in frames:
        prev.paste(f, (x, 10), f)
        prev.paste(f, (x, 306), f)
        x += f.width + 20
    prev.save(os.path.join(HERE, "ikona_nahled.png"))
    print("ulozeno", out, os.path.getsize(out), "B")


if __name__ == "__main__":
    main()
