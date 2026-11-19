"""Aviso de nova versão no canto inferior direito da janela principal."""

from __future__ import annotations

from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from app import __version__
from app.core import updater
from app.ui.widgets import MUTED_TEXT, font, run_in_background

TEAL = ("#00A3A6", "#00CBCC")
TEAL_HOVER = ("#008d90", "#00b3b4")


class UpdateToast(ctk.CTkFrame):
    """Cartão flutuante com a versão nova, um botão para atualizar e um ✕ para dispensar.

    `can_start()` é consultado antes de atualizar (ex.: impedir durante um envio). `on_installed()` é chamado
    quando a nova versão já está no lugar: deve abrir o app novo (`updater.restart()`) e fechar este.
    """

    WIDTH = 320

    def __init__(self, master, release: updater.Release, can_start: Callable[[], bool],
                 on_installed: Callable[[], None]):
        super().__init__(master, width=self.WIDTH, corner_radius=14, border_width=1,
                         fg_color=("#ffffff", "#2b2b2b"), border_color=("gray80", "#3d3d3d"))
        self.release = release
        self._can_start, self._on_installed = can_start, on_installed
        self._progress_value = 0.0
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=(16, 8), pady=(12, 0))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="", width=10, height=10, corner_radius=5, fg_color=TEAL).grid(
            row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(header, text="Nova versão disponível", font=font(14, "bold"), anchor="w").grid(
            row=0, column=1, sticky="w")
        self._close = ctk.CTkButton(header, text="✕", width=26, height=26, corner_radius=13, font=font(13),
                                    fg_color="transparent", hover_color=("gray88", "gray25"),
                                    text_color=MUTED_TEXT, command=self.dismiss)
        self._close.grid(row=0, column=2)

        self._message = ctk.CTkLabel(
            self, text=f"A versão {release.version} já pode ser instalada. Você está usando a {__version__}.",
            font=font(12), text_color=MUTED_TEXT, anchor="w", justify="left", wraplength=self.WIDTH - 32)
        self._message.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 10))

        self._progress = ctk.CTkProgressBar(self, height=6, progress_color=TEAL)
        self._progress.set(0)

        self._button = ctk.CTkButton(self, text="Atualizar agora", height=34, corner_radius=10,
                                     font=font(13, "bold"), fg_color=TEAL, hover_color=TEAL_HOVER,
                                     text_color=("#ffffff", "#0b1f1f"), command=self._start)
        self._button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))

    def show(self) -> None:
        self.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")
        self.lift()

    def dismiss(self) -> None:
        self.place_forget()
        self.destroy()

    # --- atualização ---
    def _start(self) -> None:
        if not self._can_start():
            return
        if not updater.can_self_update(self.release):
            updater.open_release_page(self.release)
            return
        self._button.configure(state="disabled", text="Baixando…")
        self._close.configure(state="disabled")
        self._message.configure(text=f"Baixando a versão {self.release.version}…")
        self._progress.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._poll_progress()
        run_in_background(self, lambda: updater.download_and_install(self.release, self._set_progress),
                          self._finished)

    def _set_progress(self, value: float) -> None:  # chamado da thread do download
        self._progress_value = value

    def _poll_progress(self) -> None:
        if not self.winfo_exists() or self._progress_value < 0:
            return
        self._progress.set(self._progress_value)
        self._button.configure(text=f"Baixando… {round(self._progress_value * 100)}%")
        self.after(150, self._poll_progress)

    def _finished(self, _result, error: BaseException | None) -> None:
        self._progress_value = -1.0  # para o acompanhamento
        if error is None:
            self._progress.set(1)
            self._button.configure(text="Reiniciando…")
            self._message.configure(text="Atualização instalada. O Certifica vai abrir de novo.")
            self.after(600, self._on_installed)
            return
        self._progress.grid_forget()
        self._button.configure(state="normal", text="Atualizar agora")
        self._close.configure(state="normal")
        self._message.configure(text=f"A versão {self.release.version} já pode ser instalada. "
                                     f"Você está usando a {__version__}.")
        detail = str(error) if isinstance(error, updater.UpdateError) else "Verifique a conexão com a internet."
        if messagebox.askyesno(
            "Não foi possível atualizar",
            f"{detail}\n\nAbrir a página de download para baixar a versão {self.release.version} manualmente?",
            parent=self.winfo_toplevel(),
        ):
            updater.open_release_page(self.release)
