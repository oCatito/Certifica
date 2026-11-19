"""Ícones das etapas do menu inicial, desenhados em vetor.

Cada ícone é descrito numa grade de 100 x 100 e pode ser desenhado de dois jeitos:

- macOS: direto no Canvas do Tk, que suaviza as bordas e desenha na resolução da tela (nítido no
  Retina). Imagens, ao contrário, aparecem borradas no Retina, porque o Tk 8.6 as amplia.
- Windows/Linux: o Canvas não suaviza bordas, então o mesmo desenho é feito com o Pillow em 4x,
  reduzido e colocado no Canvas como imagem.

As cores seguem o ícone do app (teal e dourado da roseta).
"""

from __future__ import annotations

import math
import sys
import tkinter as tk
from typing import Callable

USE_VECTOR = sys.platform == "darwin"
SS = 4  # supersampling do Pillow

Point = tuple[float, float]
Palette = dict[str, str]

_LIGHT: Palette = {
    "teal": "#00A3A6",
    "teal_dark": "#007E82",
    "teal_soft": "#BFE3E4",
    "gold": "#F2B43C",
    "gold_dark": "#D08A22",
    "gold_light": "#FFD98A",
    "paper": "#FFFFFF",
    "ink": "#9CC9CB",
    "green": "#22A04B",
    "green_light": "#9BE3B0",
}
_DARK: Palette = {
    "teal": "#00CBCC",
    "teal_dark": "#00979B",
    "teal_soft": "#A6DADB",
    "gold": "#F2B43C",
    "gold_dark": "#D8922A",
    "gold_light": "#FFD27A",
    "paper": "#F2F6F6",
    "ink": "#A9CED0",
    "green": "#34B85C",
    "green_light": "#A8EBBC",
}


def palette(dark: bool, disabled: bool = False, background: str = "#000000") -> Palette:
    """Cores do ícone. Desativado: tons de cinza esmaecidos contra o fundo do card."""
    base = dict(_DARK if dark else _LIGHT)
    if disabled:
        fade = 0.62 if dark else 0.45
        base = {k: _mix(_gray(v), background, fade) for k, v in base.items()}
    return base


# ---------------------------------------------------------------- formas


def rounded_rect(x0: float, y0: float, x1: float, y1: float, r: float, steps: int = 8) -> list[Point]:
    pts: list[Point] = []
    corners = ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180))
    for cx, cy, start in corners:
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _star(cx: float, cy: float, r: float, inner: float, points: int) -> list[Point]:
    pts = []
    for i in range(points * 2):
        a = math.pi * i / points - math.pi / 2
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _folded_sheet(x0: float, y0: float, x1: float, y1: float, r: float, fold: float,
                  r_fold: float) -> tuple[list[Point], list[Point]]:
    """Folha com o canto superior direito dobrado, para a caneta `rounded`.

    Devolve (miolo da folha, miolo da dobra): cada miolo é a forma encolhida do seu raio (`r` e
    `r_fold`); a caneta engorda de volta com as quinas redondas, e o resultado cobre exatamente
    o retângulo (x0, y0)-(x1, y1) com o canto superior direito cortado em `fold`.
    """
    k = math.sqrt(2)
    sheet = [(x0 + r, y0 + r), (x1 - fold + r * (1 - k), y0 + r), (x1 - r, y0 + fold + r * (k - 1)),
             (x1 - r, y1 - r), (x0 + r, y1 - r)]
    f = r_fold
    tri = [(x1 - fold + f, y0 + fold - f), (x1 - fold + f, y0 + f * (1 + k)), (x1 - f * (1 + k), y0 + fold - f)]
    return sheet, tri


# ---------------------------------------------------------------- canetas


class _CanvasPen:
    """No macOS o Tk só suaviza formas com contorno de largura > 0 (tk::mac::CGAntialiasLimit).
    Formas só com preenchimento ganham um contorno de 1 pt da mesma cor."""

    def __init__(self, canvas: tk.Canvas, size: float):
        self.c, self.k = canvas, size / 100

    def _xy(self, pts: list[Point]) -> list[float]:
        return [v * self.k for p in pts for v in p]

    def _stroke(self, fill: str, outline: str, width: float) -> tuple[str, float]:
        if outline and width:
            return outline, width * self.k
        return fill, 1

    def poly(self, pts: list[Point], fill: str = "", outline: str = "", width: float = 0) -> None:
        outline, w = self._stroke(fill, outline, width)
        self.c.create_polygon(self._xy(pts), fill=fill, outline=outline, width=w, joinstyle="round")

    def line(self, pts: list[Point], color: str, width: float) -> None:
        self.c.create_line(self._xy(pts), fill=color, width=width * self.k, capstyle="round", joinstyle="round")

    def circle(self, cx: float, cy: float, r: float, fill: str = "", outline: str = "", width: float = 0) -> None:
        k = self.k
        outline, w = self._stroke(fill, outline, width)
        self.c.create_oval((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k, fill=fill, outline=outline, width=w)

    def rounded(self, pts: list[Point], r: float, fill: str) -> None:
        """Polígono `pts` engordado em `r`, com as quinas redondas.

        O Tk arredonda cada ponto de um polígono para um número inteiro de pontos, então um arco
        pequeno (canto arredondado) vira uns poucos degraus: o canto fica "cortado". Já a junção
        redonda de um contorno grosso é desenhada como curva de verdade, sem esse problema."""
        self.c.create_polygon(self._xy(pts), fill=fill, outline=fill, width=2 * r * self.k, joinstyle="round")


class _ImagePen:
    def __init__(self, size_px: int):
        from PIL import Image, ImageDraw

        self.k = size_px * SS / 100
        self.img = Image.new("RGBA", (size_px * SS, size_px * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _xy(self, pts: list[Point]) -> list[Point]:
        return [(x * self.k, y * self.k) for x, y in pts]

    def poly(self, pts: list[Point], fill: str = "", outline: str = "", width: float = 0) -> None:
        xy = self._xy(pts)
        if fill:
            self.d.polygon(xy, fill=fill)
        if outline and width:
            self.line(pts + pts[:1], outline, width)

    def line(self, pts: list[Point], color: str, width: float) -> None:
        w = width * self.k
        xy = self._xy(pts)
        self.d.line(xy, fill=color, width=round(w), joint="curve")
        for x, y in (xy[0], xy[-1]):
            self.d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)

    def circle(self, cx: float, cy: float, r: float, fill: str = "", outline: str = "", width: float = 0) -> None:
        k = self.k
        box = ((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k)
        self.d.ellipse(box, fill=fill or None, outline=outline or None, width=round(width * k) if outline else 0)

    def rounded(self, pts: list[Point], r: float, fill: str) -> None:
        """Polígono `pts` engordado em `r`, com as quinas redondas (o mesmo resultado da _CanvasPen)."""
        self.poly(pts, fill=fill)
        for a, b in zip(pts, pts[1:] + pts[:1]):
            self.line([a, b], fill, 2 * r)


# ---------------------------------------------------------------- ícones


def _list_icon(p, c: Palette) -> None:
    """Folha dobrada com uma lista e um "+" dourado (nova lista)."""
    body, fold = _folded_sheet(14, 8, 76, 90, r=8, fold=18, r_fold=1.5)
    p.rounded(body, 8, c["teal"])
    p.rounded(fold, 1.5, c["teal_soft"])
    # linhas: marcador + texto (a última é mais curta para não encostar no "+")
    for y, end in ((38, 62), (52, 62), (66, 54)):
        p.circle(26, y, 3.6, fill=c["paper"])
        p.line([(36, y), (end, y)], c["paper"], 5)
    # "+" dourado com contorno claro, para se destacar da folha
    p.line([(72, 68), (72, 92)], c["paper"], 15)
    p.line([(60, 80), (84, 80)], c["paper"], 15)
    p.line([(72, 69), (72, 91)], c["gold"], 9)
    p.line([(61, 80), (83, 80)], c["gold"], 9)


def _certificate_icon(p, c: Palette) -> None:
    """Certificado com a roseta do app."""
    p.poly(rounded_rect(6, 16, 94, 76, 6), fill=c["paper"], outline=c["teal"], width=4)
    p.poly(rounded_rect(13, 23, 87, 69, 3), outline=c["teal_soft"], width=1.6)
    p.line([(23, 37), (62, 37)], c["teal"], 5.5)
    p.line([(23, 49), (54, 49)], c["ink"], 4)
    p.line([(23, 59), (46, 59)], c["ink"], 4)
    # fitas
    for x0, x1, col in ((67, 61, c["gold_dark"]), (77, 83, c["gold"])):
        w = 8
        p.poly([(x0 - w / 2, 68), (x0 + w / 2, 68), (x1 + w / 2, 94), (x1, 89), (x1 - w / 2, 94)], fill=col)
    # roseta serrilhada com anel
    p.poly(_star(72, 64, 17, 0.88, 18), fill=c["gold"])
    p.circle(72, 64, 11, outline=c["gold_light"], width=2.4)


def _send_icon(p, c: Palette) -> None:
    """Envelope voando, com linhas de velocidade douradas."""
    # corpo (22, 23)-(90, 77) com cantos de raio 8: `rounded` engorda o miolo de volta até a borda.
    # O envelope fica quase no centro; as linhas, curtas, ocupam a margem da esquerda.
    r = 8
    p.rounded([(22 + r, 23 + r), (90 - r, 23 + r), (90 - r, 77 - r), (22 + r, 77 - r)], r, c["teal"])
    p.line([(31, 32), (56, 54), (81, 32)], c["paper"], 5.5)  # aba em V
    for x, y in ((9, 37), (4, 50), (9, 63)):
        p.line([(x, y), (15, y)], c["gold"], 5)


def _upload_icon(p, c: Palette) -> None:
    """Planilha (folha com grade) e um círculo dourado com seta para cima (carregar)."""
    body, fold = _folded_sheet(12, 6, 70, 86, r=7, fold=17, r_fold=1.5)
    p.rounded(body, 7, c["teal"])
    p.rounded(fold, 1.5, c["teal_soft"])
    # grade da planilha: cabeçalho mais grosso e linhas finas
    p.line([(22, 36), (58, 36)], c["paper"], 5)
    for y in (48, 59, 70):
        p.line([(22, y), (50, y)], c["paper"], 3)
    p.line([(36, 44), (36, 74)], c["paper"], 3)
    # círculo dourado com seta, com borda clara para se destacar da folha
    p.circle(70, 72, 22, fill=c["paper"])
    p.circle(70, 72, 18, fill=c["gold"])
    p.line([(70, 83), (70, 62)], c["paper"], 6)
    p.line([(61, 70), (70, 61), (79, 70)], c["paper"], 6)


def _done_badge(p, c: Palette) -> None:
    """Roseta verde com um check: etapa concluída."""
    p.poly(_star(50, 50, 48, 0.86, 16), fill=c["green"])
    p.circle(50, 50, 34, outline=c["green_light"], width=3)
    p.line([(33, 51), (45, 63), (68, 38)], c["paper"], 9)


ICONS: dict[str, Callable] = {
    "upload": _upload_icon,
    "list": _list_icon,
    "certificate": _certificate_icon,
    "send": _send_icon,
    "done": _done_badge,
}


def draw_icon(canvas: tk.Canvas, name: str, size_px: int, colors: Palette) -> None:
    """Desenha o ícone ocupando o Canvas inteiro (size_px x size_px)."""
    canvas.delete("all")
    if USE_VECTOR:
        ICONS[name](_CanvasPen(canvas, size_px), colors)
        return
    from PIL import Image, ImageTk

    pen = _ImagePen(size_px)
    ICONS[name](pen, colors)
    image = ImageTk.PhotoImage(pen.img.resize((size_px, size_px), Image.LANCZOS))
    canvas.create_image(0, 0, image=image, anchor="nw")
    canvas._icon_image = image  # type: ignore[attr-defined]  # o Tk não guarda a referência


# ---------------------------------------------------------------- cores


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def _gray(color: str) -> str:
    r, g, b = _rgb(color)
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return _hex((y, y, y))


def _mix(color: str, other: str, t: float) -> str:
    """Mistura `color` com `other` (t=0 → color, t=1 → other)."""
    a, b = _rgb(color), _rgb(other)
    return _hex(x + (y - x) * t for x, y in zip(a, b))
