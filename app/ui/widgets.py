"""Componentes de interface reutilizáveis."""

from __future__ import annotations

import threading
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
