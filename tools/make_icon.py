"""Gera assets/icon.png, icon.ico e icon.icns (requer Pillow: pip install pillow)."""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZE = 1024
# Grade de ícones do macOS: numa tela de 1024 px, o fundo arredondado ocupa 824 px (100 px de margem
# transparente) e leva uma sombra leve. Sem essa margem o ícone fica maior que os outros no Dock.
MAC_BODY = 824
# Desenha em 4x e reduz no fim: o Pillow não suaviza bordas de polígonos e linhas.
SS = 4

# Ícone "roseta com check": cores e formas definidas aqui mesmo (não dependem de nenhum SVG)
BG_TOP, BG_BOTTOM = (0x00, 0xCB, 0xCC), (0x00, 0x9A, 0x9E)
GOLD, GOLD_DARK, GOLD_LIGHT = (0xF2, 0xB4, 0x3C), (0xD8, 0x92, 0x2A), (0xFF, 0xD2, 0x7A)
WHITE = (255, 255, 255)


def _s(*values: float) -> list[float]:
    return [v * SS for v in values]


def _seal(d: ImageDraw.ImageDraw, color=None) -> None:
    """Roseta dourada com fitas e check. Com `color`, desenha tudo numa cor só (máscara da sombra)."""
    pick = (lambda c: color) if color is not None else (lambda c: c)
    # fitas com ponta recortada
    cx, cy, r = 512, 520, 230
    for side, col in ((-1, GOLD_DARK), (1, GOLD)):
        x0, x1, w = cx + side * r * 0.15, cx + side * r * 0.5, r * 0.42
        yb, notch = cy + r * 1.45, r * 0.22
        pts = [(x0 - w / 2, cy), (x0 + w / 2, cy), (x1 + w / 2, yb), (x1, yb - notch), (x1 - w / 2, yb)]
        d.polygon([(x * SS, y * SS) for x, y in pts], fill=pick(col))
    # roseta serrilhada (24 pontas)
    cx, cy, r, points = 512, 440, 270, 24
    pts = []
    for i in range(points * 2):
        a = math.pi * i / points - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.91
        pts.append(((cx + rr * math.cos(a)) * SS, (cy + rr * math.sin(a)) * SS))
    d.polygon(pts, fill=pick(GOLD))
    # anel claro
    d.ellipse(_s(cx - 211, cy - 211, cx + 211, cy + 211), outline=pick(GOLD_LIGHT), width=22 * SS)
    # check com pontas arredondadas
    s, w = 150, 48
    chk = [(cx - s * 0.52, cy + s * 0.02), (cx - s * 0.14, cy + s * 0.40), (cx + s * 0.56, cy - s * 0.34)]
    chk = [(x * SS, y * SS) for x, y in chk]
    d.line(chk, fill=pick(WHITE), width=w * SS, joint="curve")
    for x, y in (chk[0], chk[-1]):
        d.ellipse((x - w * SS / 2, y - w * SS / 2, x + w * SS / 2, y + w * SS / 2), fill=pick(WHITE))


def draw() -> Image.Image:
    big = SIZE * SS
    # fundo arredondado com degradê vertical
    grad = Image.new("RGBA", (1, big))
    for y in range(big):
        t = y / (big - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,))
    grad = grad.resize((big, big))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(_s(40, 40, SIZE - 40, SIZE - 40), radius=210 * SS, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    # sombra suave do selo
    shadow_mask = Image.new("L", (big, big), 0)
    _seal(ImageDraw.Draw(shadow_mask), color=56)  # ~22% de opacidade
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(14 * SS))
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 255))
    shadow.putalpha(shadow_mask)
    img.alpha_composite(shadow, (0, 10 * SS))
    _seal(ImageDraw.Draw(img))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def mac_icon(img: Image.Image) -> Image.Image:
    """Reduz o desenho para a área de 824 px da grade da Apple, centralizado, com sombra suave."""
    body = img.crop((40, 40, SIZE - 40, SIZE - 40)).resize((MAC_BODY, MAC_BODY), Image.LANCZOS)
    offset = (SIZE - MAC_BODY) // 2
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    alpha = body.getchannel("A").point(lambda a: a * 0.3)
    shadow.paste((0, 0, 0, 255), (offset, offset + 12), alpha)
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.alpha_composite(body, (offset, offset))
    return canvas


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    img = draw()
    mac = mac_icon(img)
    # icon.png é usado pelo app aberto em macOS/Linux (iconphoto); icon.icns pelo .app do macOS.
    mac.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    mac.save(ASSETS / "icon.icns")
    # No Windows os ícones ocupam quase todo o quadro: mantém o desenho sem a margem do macOS.
    img.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Ícones gerados em", ASSETS)


if __name__ == "__main__":
    main()
