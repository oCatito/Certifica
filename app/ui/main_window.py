"""Janela principal: nome do app no topo, as 3 etapas em cards quadrados e engrenagem de configurações."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from app import APP_TITLE, __version__
from app.core.config import get_password, load_config
from app.paths import resource_path
from app.ui import icons
from app.ui.macos import set_app_name
from app.ui.widgets import MUTED_TEXT, OK_COLOR, font

TEAL = ("#00A3A6", "#00CBCC")  # cor da marca (ícone do app)
_POINTER = "pointinghand" if sys.platform == "darwin" else "hand2"


class StepCard(ctk.CTkFrame):
    """Botão quadrado de uma etapa: número, ícone, nome e situação.

    Sem `command`, a etapa aparece desativada (ícone em cinza, sem clique). Concluída (`status="done"`),
    o card inteiro fica esverdeado, com uma roseta verde com check no canto inferior direito.
    """

    SIZE = 220
    ICON = 96
    BADGE = 46
    _BG = ("#ffffff", "#2b2b2b")
    _BG_HOVER = ("#f2fafa", "#2f3637")
    _BG_OFF = ("gray95", "#272727")
    _BORDER = ("gray82", "#3a3a3a")
    _BORDER_OFF = ("gray87", "#303030")
    _BG_DONE = ("#e6f5ea", "#223a29")
    _BG_DONE_HOVER = ("#d9f0e0", "#27442f")
    _BORDER_DONE = ("#8fd3a2", "#3b7f4e")

    def __init__(self, master, number: int, title: str, icon: str,
                 command: Callable[[], None] | None = None, status: str | None = None):
        self._enabled = command is not None
        self._done = self._enabled and status == "done"
        self._command, self._icon, self._hover = command, icon, False
        super().__init__(
            master,
            width=self.SIZE,
            height=self.SIZE,
            corner_radius=18,
            border_width=2,
            fg_color=self._bg(),
            border_color=self._border(),
        )
        muted = MUTED_TEXT if self._enabled else ("gray62", "gray40")
        if self._done:
            number_bg, number_fg = ("#cdebd6", "#2e5038"), OK_COLOR
        elif self._enabled:
            number_bg, number_fg = ("gray91", "#383838"), muted
        else:
            number_bg, number_fg = ("gray89", "#2e2e2e"), muted

        ctk.CTkLabel(
            self, text=str(number), width=26, height=26, corner_radius=13, font=font(13, "bold"),
            fg_color=number_bg, text_color=number_fg,
        ).place(x=16, y=16)
        if status == "soon":
            self._pill("Em breve", ("gray88", "#333333"), muted)

        self._icon_canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._icon_canvas.place(relx=0.5, rely=0.44, anchor="center")
        self._badge_canvas: tk.Canvas | None = None
        if self._done:
            self._badge_canvas = tk.Canvas(self, highlightthickness=0, bd=0)
            self._badge_canvas.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
        self._draw_icon()

        ctk.CTkLabel(
            self, text=title, font=font(16, "bold"), wraplength=self.SIZE - 32,
            text_color=None if self._enabled else muted,
        ).place(relx=0.5, y=176, anchor="center")

        if self._enabled:
            for widget in self._tk_widgets(self):
                tk.Misc.configure(widget, cursor=_POINTER)
                tk.Misc.bind(widget, "<Enter>", lambda _e: self._set_hover(True), add="+")
                tk.Misc.bind(widget, "<Leave>", lambda _e: self.after(20, self._check_pointer), add="+")
                tk.Misc.bind(widget, "<ButtonRelease-1>", self._on_click, add="+")

    def _pill(self, text: str, fg_color, text_color) -> None:
        ctk.CTkLabel(self, text=text, height=24, corner_radius=12, font=font(12, "bold"),
                     fg_color=fg_color, text_color=text_color).place(relx=1.0, x=-16, y=17, anchor="ne")

    @classmethod
    def _tk_widgets(cls, widget: tk.Misc) -> list[tk.Misc]:
        """O card e todos os widgets do Tk dentro dele (inclusive os internos do CustomTkinter)."""
        found = [widget]
        for child in tk.Misc.winfo_children(widget):
            found += cls._tk_widgets(child)
        return found

    def _bg(self):
        if not self._enabled:
            return self._BG_OFF
        if self._done:
            return self._BG_DONE_HOVER if self._hover else self._BG_DONE
        return self._BG_HOVER if self._hover else self._BG

    def _border(self):
        if not self._enabled:
            return self._BORDER_OFF
        if self._done:
            return OK_COLOR if self._hover else self._BORDER_DONE
        return TEAL if self._hover else self._BORDER

    def _draw_icon(self) -> None:
        size = self._apply_widget_scaling(self.ICON)
        bg = self._apply_appearance_mode(self._bg())
        self._icon_canvas.configure(width=size, height=size, bg=bg)
        # O fundo pode ser um nome de cor do Tk ("gray95"); a paleta só mistura cores em hex.
        bg_hex = "#%02x%02x%02x" % tuple(v // 257 for v in self.winfo_rgb(bg))
        colors = icons.palette(self._get_appearance_mode() == "dark", disabled=not self._enabled, background=bg_hex)
        icons.draw_icon(self._icon_canvas, self._icon, size, colors)
        if self._badge_canvas is not None:
            badge = self._apply_widget_scaling(self.BADGE)
            self._badge_canvas.configure(width=badge, height=badge, bg=bg)
            icons.draw_icon(self._badge_canvas, "done", badge, colors)

    def _pointer_inside(self) -> bool:
        x, y = self.winfo_pointerxy()
        x0, y0 = self.winfo_rootx(), self.winfo_rooty()
        return x0 <= x < x0 + self.winfo_width() and y0 <= y < y0 + self.winfo_height()

    def _check_pointer(self) -> None:
        # <Leave> também chega ao passar de um widget interno para outro: só sai do hover fora do card.
        try:
            if self.winfo_exists() and not self._pointer_inside():
                self._set_hover(False)
        except tk.TclError:
            pass

    def _set_hover(self, on: bool) -> None:
        if on == self._hover:
            return
        self._hover = on
        self.configure(fg_color=self._bg(), border_color=self._border())
        bg = self._apply_appearance_mode(self._bg())
        self._icon_canvas.configure(bg=bg)
        if self._badge_canvas is not None:
            self._badge_canvas.configure(bg=bg)

    def _on_click(self, _event=None) -> None:
        if self._pointer_inside():  # como num botão: soltar fora do card cancela o clique
            self._command()

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "_icon_canvas"):
            self._draw_icon()

    def _set_scaling(self, new_widget_scaling, new_window_scaling) -> None:
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "_icon_canvas"):
            self._draw_icon()


class HomePage(ctk.CTkFrame):
    def __init__(self, master: "MainWindow"):
        super().__init__(master, fg_color="transparent")
        self.app = master

        ctk.CTkLabel(self, text=APP_TITLE, font=font(30, "bold")).place(relx=0.5, y=46, anchor="center")
        gear = ctk.CTkButton(
            self,
            text="⚙",
            width=44,
            height=44,
            corner_radius=22,
            font=font(22),
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            text_color=("gray20", "gray85"),
            command=master.open_settings,
        )
        gear.place(relx=1.0, x=-20, y=24, anchor="ne")  # centro na mesma altura do título

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.52, anchor="center")

        # Cada etapa é independente: dá para fazer só uma delas, em qualquer ordem.
        sheet = master.list_sheet
        steps = [
            ("Planilhar", "list", master.open_list, "done" if sheet is not None else None),
            ("Certificar", "certificate", None, "soon"),
            ("Enviar", "send", master.open_send, None),
        ]
        row = ctk.CTkFrame(center, fg_color="transparent")
        row.pack()
        for i, (title, icon, command, status) in enumerate(steps):
            StepCard(row, i + 1, title, icon, command, status).grid(row=0, column=i, padx=12)

        # Linha sempre presente (vazia sem lista) para os cards não mudarem de lugar.
        info = f"Lista: {sheet.path.name} · {len(sheet.rows)} pessoa(s)" if sheet is not None else ""
        ctk.CTkLabel(center, text=info, font=font(12), text_color=MUTED_TEXT).pack(pady=(16, 0))

        ctk.CTkLabel(self, text=f"versão {__version__}", font=font(11), text_color=MUTED_TEXT).place(
            relx=0.0, rely=1.0, x=16, y=-10, anchor="sw"
        )


try:
    from tkinterdnd2 import TkinterDnD

    _DnDBase = TkinterDnD.DnDWrapper
except Exception:  # noqa: BLE001 - sem arrastar e soltar, o resto do app funciona igual
    TkinterDnD = None
    _DnDBase = object


class MainWindow(ctk.CTk, _DnDBase):
    def __init__(self):
        super().__init__()
        self.dnd_available = self._enable_dnd()
        self.title(APP_TITLE)
        self.geometry("1000x700")
        self.minsize(860, 620)
        self._set_icon()

        self.config_data = load_config()
        self.list_sheet = None  # lista confirmada na etapa 1 (vale enquanto o app estiver aberto)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.page: ctk.CTkFrame | None = None
        self.show_home()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _enable_dnd(self) -> bool:
        """Ativa o arrastar e soltar de arquivos (tkdnd). Se falhar, só o clique fica disponível."""
        if TkinterDnD is None:
            return False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _set_icon(self) -> None:
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(str(resource_path("assets/icon.ico")))
            else:
                self._icon = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
                self.iconphoto(True, self._icon)
        except (tk.TclError, OSError):
            pass

    def _show(self, page: ctk.CTkFrame) -> None:
        if self.page is not None:
            self.page.destroy()
        self.page = page
        page.grid(row=0, column=0, sticky="nsew")

    def show_home(self) -> None:
        self._show(HomePage(self))

    def open_settings(self) -> None:
        from app.ui.settings_window import SettingsPage

        self._show(SettingsPage(self, self.config_data, on_saved=self._on_settings_saved, on_exit=self.show_home))

    def _on_settings_saved(self, cfg) -> None:
        self.config_data = cfg

    def open_list(self) -> None:
        from app.ui.list_wizard import ListWizard

        self._show(ListWizard(self, on_exit=self.show_home, on_confirm=self.complete_list, initial=self.list_sheet))

    def complete_list(self, sheet) -> None:
        self.list_sheet = sheet
        self.show_home()

    def open_send(self) -> None:
        cfg = self.config_data
        reason = cfg.smtp_incomplete_reason(
            has_password=not cfg.smtp.auth or bool(get_password(cfg.smtp.username)))
        if reason:
            if messagebox.askyesno(
                "Configurações incompletas",
                f"Antes de enviar, configure o email: {reason}.\n\nAbrir as configurações agora?",
                parent=self,
            ):
                self.open_settings()
            return
        from app.ui.send_wizard import SendWizard

        self._show(SendWizard(self, on_exit=self.show_home))

    def on_close(self) -> None:
        page = self.page
        if getattr(page, "is_sending", False):
            if not messagebox.askyesno(
                "Envio em andamento",
                "Há um envio em andamento. Deseja cancelar o envio e fechar o programa?\n\n"
                "Quem já recebeu fica registrado e não receberá de novo.",
                parent=self,
            ):
                return
            page.stop_sending()
        self.destroy()


def run() -> None:
    set_app_name(APP_TITLE)  # antes de criar a janela: o Tk lê o nome ao iniciar
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    MainWindow().mainloop()
