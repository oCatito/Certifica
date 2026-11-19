"""Componentes de interface reutilizáveis."""

from __future__ import annotations

import math
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import customtkinter as ctk

ACCENT = ("#1f6aa5", "#1f6aa5")
MUTED_TEXT = ("gray40", "gray65")
CARD_COLOR = ("gray92", "gray17")
OK_COLOR = ("#1e7b34", "#4cc06a")
ERROR_COLOR = ("#b3261e", "#ff6b61")
WARN_COLOR = ("#8a5a00", "#f0b44c")


def font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def is_dark() -> bool:
    return ctk.get_appearance_mode().lower() == "dark"


def run_in_background(
    widget: tk.Misc,
    func: Callable[[], Any],
    on_done: Callable[[Any, BaseException | None], None],
) -> None:
    """Executa func numa thread e chama on_done(resultado, erro) de volta na thread da interface."""
    box: dict[str, Any] = {}

    def target():
        try:
            box["value"] = func()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    def poll():
        if thread.is_alive():
            widget.after(100, poll)
        else:
            on_done(box.get("value"), box.get("error"))

    widget.after(100, poll)


class Card(ctk.CTkFrame):
    def __init__(self, master, title: str | None = None, **kwargs):
        super().__init__(master, fg_color=CARD_COLOR, corner_radius=12, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(self, text=title, font=font(15, "bold"), anchor="w").grid(
                row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(12, 4)
            )


class Table(ctk.CTkFrame):
    """Tabela (ttk.Treeview) com rolagem e cores que acompanham o modo claro/escuro."""

    _style_ready = False

    def __init__(self, master, columns: list[tuple[str, str, int]], height: int = 12):
        super().__init__(master, fg_color="transparent")
        self._configure_style()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self, columns=[c[0] for c in columns], show="headings", height=height, style="Cert.Treeview"
        )
        for key, title, width in columns:
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=width, minwidth=50, anchor="w", stretch=True)
        yscroll = ctk.CTkScrollbar(self, command=self.tree.yview)
        xscroll = ctk.CTkScrollbar(self, command=self.tree.xview, orientation="horizontal")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        dark = is_dark()
        self.tree.tag_configure("error", foreground="#ff6b61" if dark else "#b3261e")
        self.tree.tag_configure("warn", foreground="#f0b44c" if dark else "#8a5a00")
        self.tree.tag_configure("muted", foreground="gray60" if dark else "gray45")

    @staticmethod
    def _configure_style() -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        dark = is_dark()
        bg, fg = ("#242424", "#dce4ee") if dark else ("#ffffff", "#1a1a1a")
        head_bg = "#333333" if dark else "#e6e6e6"
        style.configure(
            "Cert.Treeview",
            background=bg,
            fieldbackground=bg,
            foreground=fg,
            rowheight=28,
            borderwidth=0,
            font=("TkDefaultFont", 12),
        )
        style.configure(
            "Cert.Treeview.Heading",
            background=head_bg,
            foreground=fg,
            relief="flat",
            font=("TkDefaultFont", 12, "bold"),
        )
        style.map("Cert.Treeview", background=[("selected", "#1f6aa5")], foreground=[("selected", "#ffffff")])
        style.map("Cert.Treeview.Heading", background=[("active", head_bg)])

    def set_rows(self, rows: list[tuple[tuple, str | None]]) -> None:
        """rows: lista de (valores, tag)."""
        self.tree.delete(*self.tree.get_children())
        for values, tag in rows:
            self.tree.insert("", "end", values=values, tags=(tag,) if tag else ())


class LogBox(ctk.CTkTextbox):
    """Caixa de log somente leitura com cores por nível."""

    MAX_LINES = 3000

    def __init__(self, master, **kwargs):
        super().__init__(master, wrap="word", font=ctk.CTkFont(family="Menlo", size=12), **kwargs)
        dark = is_dark()
        self.tag_config("ok", foreground="#4cc06a" if dark else "#1e7b34")
        self.tag_config("error", foreground="#ff6b61" if dark else "#b3261e")
        self.tag_config("warn", foreground="#f0b44c" if dark else "#8a5a00")
        self.configure(state="disabled")

    def append(self, text: str, level: str = "info") -> None:
        self.configure(state="normal")
        self.insert("end", text + "\n", (level,) if level != "info" else ())
        lines = int(self.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self.delete("1.0", f"{lines - self.MAX_LINES}.0")
        self.see("end")
        self.configure(state="disabled")


def set_readonly_text(box: ctk.CTkTextbox, text: str) -> None:
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.configure(state="disabled")


def countdown_text(seconds: float) -> str:
    """Texto do centro do timer: “42” abaixo de um minuto, “1:05” a partir dele (arredonda para cima)."""
    total = max(0, math.ceil(seconds - 1e-9))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}" if minutes else str(secs)


RING_SUPERSAMPLE = 4  # desenha 4x maior e reduz: bordas lisas (o Tk não suaviza arcos)


def render_ring(size: int, thickness: float, frac: float, color: str, background: str):
    """Imagem (Pillow) do anel do timer: `frac` de 0 a 1 é quanto da borda ainda aparece.

    A borda começa no topo e segue no sentido horário, com as pontas arredondadas. Cores em hex.
    """
    from PIL import Image, ImageDraw

    ss = RING_SUPERSAMPLE
    big = size * ss
    img = Image.new("RGB", (big, big), background)
    frac = min(1.0, max(0.0, frac))
    if frac > 0:
        draw = ImageDraw.Draw(img)
        width = thickness * ss
        margin = ss  # 1 px de folga para a suavização não ser cortada na borda da imagem
        start, end = -90.0, -90.0 + 360.0 * frac  # Pillow: graus no sentido horário a partir das 3h
        draw.arc((margin, margin, big - margin - 1, big - margin - 1), start, end, fill=color, width=round(width))
        if frac < 1:
            center = (big - 1) / 2
            radius = (big - 2 * margin) / 2 - width / 2  # meio da espessura da borda
            for angle in (start, end):
                x = center + radius * math.cos(math.radians(angle))
                y = center + radius * math.sin(math.radians(angle))
                draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=color)
    return img.reduce(ss)


class CountdownRing(ctk.CTkFrame):
    """Timer circular: a borda começa cheia e vai sumindo até o tempo acabar, com o contador no meio.

    `start(segundos)` inicia (ou reinicia) a contagem; `stop()` para e apaga o anel. `on_finish` é chamado
    quando o tempo chega a zero.
    """

    COLOR = ("#00A3A6", "#00CBCC")  # cor da marca
    FRAME_MS = 16  # ~60 quadros por segundo

    def __init__(self, master, size: int = 140, thickness: int = 10, caption: str = "",
                 on_finish: Callable[[], None] | None = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._size, self._thickness, self._caption = size, thickness, caption
        self.on_finish = on_finish
        self._total = 0.0
        self._deadline: float | None = None
        self._job: str | None = None
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._canvas.pack()
        self._remaining = 0.0
        self._build()

    # --- desenho ---
    def _hex(self, color) -> str:
        """Cor do CTk (par claro/escuro ou nome do Tk, como "gray92") em hex, que é o que o Pillow entende."""
        return "#%02x%02x%02x" % tuple(v // 257 for v in self.winfo_rgb(self._apply_appearance_mode(color)))

    def _build(self) -> None:
        from PIL import ImageTk

        c = self._canvas
        c.delete("all")
        self._px = round(self._apply_widget_scaling(self._size))
        self._thickness_px = self._apply_widget_scaling(self._thickness)
        self._bg_hex = self._hex(self._detect_color_of_master())  # fundo de quem está por trás
        self._color_hex = self._hex(self.COLOR)
        c.configure(width=self._px, height=self._px, bg=self._bg_hex)
        # Um passo por meio pixel de circunferência: redesenhar mais que isso não muda nada na tela.
        self._steps = max(1, round(math.pi * self._px * 2))
        self._drawn_step: int | None = None
        self._photo = ImageTk.PhotoImage(render_ring(self._px, self._thickness_px, 0, self._color_hex, self._bg_hex),
                                         master=c)
        c.create_image(0, 0, image=self._photo, anchor="nw")
        size = self._px
        center_y = size / 2 - (size * 0.06 if self._caption else 0)
        self._number = c.create_text(size / 2, center_y, text="", fill=self._apply_appearance_mode(("gray10", "gray92")),
                                     font=("TkDefaultFont", -round(size * 0.24), "bold"))
        self._label = c.create_text(size / 2, size / 2 + size * 0.17, text=self._caption,
                                    fill=self._apply_appearance_mode(MUTED_TEXT),
                                    font=("TkDefaultFont", -round(size * 0.085)))
        self._paint()

    def _paint(self) -> None:
        frac = self._remaining / self._total if self._total > 0 else 0.0
        frac = min(1.0, max(0.0, frac))
        step = math.ceil(frac * self._steps)  # arredonda para cima: só some de vez no zero
        if step != self._drawn_step:
            self._drawn_step = step
            self._photo.paste(render_ring(self._px, self._thickness_px, step / self._steps,
                                          self._color_hex, self._bg_hex))
        active = self._total > 0
        self._canvas.itemconfigure(self._number, text=countdown_text(self._remaining) if active else "")
        self._canvas.itemconfigure(self._label, state="normal" if active else "hidden")

    # --- controle ---
    def start(self, seconds: float) -> None:
        self.stop()
        self._total = max(0.0, float(seconds))
        self._remaining = self._total
        self._deadline = time.monotonic() + self._total
        self._paint()
        self._tick()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._deadline = None
        self._remaining = 0.0
        self._total = 0.0
        self._paint()

    @property
    def running(self) -> bool:
        return self._deadline is not None

    def _tick(self) -> None:
        self._job = None
        if self._deadline is None or not self.winfo_exists():
            return
        self._remaining = max(0.0, self._deadline - time.monotonic())
        self._paint()
        if self._remaining <= 0:
            self._deadline = None
            if self.on_finish:
                self.on_finish()
            return
        self._job = self.after(self.FRAME_MS, self._tick)

    def destroy(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        super().destroy()

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "_canvas"):
            self._build()

    def _set_scaling(self, new_widget_scaling, new_window_scaling) -> None:
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "_canvas"):
            self._build()
