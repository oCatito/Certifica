"""Fluxo "Planilhar": baixar o modelo e carregar a planilha preenchida.

Layout: à esquerda, o guia (passo 1: o modelo e as colunas); à direita, a área de trabalho
(passo 2: arrastar a planilha e conferir a prévia). Usa as cores da marca (teal do ícone).
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from app.core.list_template import TEMPLATE_COLUMNS, TEMPLATE_FILENAME, missing_columns, write_template
from app.core.spreadsheet import Sheet, SpreadsheetError, read_sheet
from app.core.text import variable_key
from app.paths import open_path
from app.ui import icons
from app.ui.widgets import ERROR_COLOR, MUTED_TEXT, OK_COLOR, Table, font

SHEET_SUFFIXES = (".xlsx", ".xlsm", ".csv")
PREVIEW_ROWS = 200
GUIDE_WIDTH = 320
MAX_CHIPS = 7

_POINTER = "pointinghand" if sys.platform == "darwin" else "hand2"

# Cores (claro, escuro). O teal é o da marca, o mesmo dos cards do menu.
TEAL = ("#00A3A6", "#00CBCC")
BTN = ("#00868A", "#008A8D")
BTN_HOVER = ("#006F72", "#00A0A3")
PANEL = ("#ffffff", "#2b2b2b")
PANEL_BORDER = ("gray85", "#363636")
TEXT = ("gray10", "gray92")
ZONE_FILL = ("#f6fafa", "#262a2b")
ZONE_HOVER = ("#e3f4f4", "#1f3536")
ZONE_BORDER = ("#a9cfd0", "#3f5a5b")
BADGE_BG = ("#dff2f2", "#1e3a3b")
CHIP_OK = (("#dcf1e1", "#21402a"), OK_COLOR)
CHIP_MISSING = (("#fbe1df", "#4a2421"), ERROR_COLOR)
CHIP_EXTRA = (("gray90", "#353535"), ("gray25", "gray80"))
ALERT_BG = ("#fdecea", "#3a2120")

COLUMN_HELP = {
    "nome": "Nome completo, como sai no certificado",
    "email": "Endereço que vai receber o certificado",
    "arquivo_certificado": "Nome do PDF da pessoa, sem o \".pdf\"",
}


def window_bg() -> tuple[str, str]:
    return tuple(ctk.ThemeManager.theme["CTk"]["fg_color"])  # type: ignore[return-value]


def primary_button(master, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 38)
    return ctk.CTkButton(master, fg_color=BTN, hover_color=BTN_HOVER, text_color="white", corner_radius=10,
                         font=font(14, "bold"), **kwargs)


def ghost_button(master, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 32)
    return ctk.CTkButton(master, fg_color="transparent", hover_color=("gray88", "gray25"), border_width=1,
                         border_color=("gray75", "gray35"), text_color=TEXT, corner_radius=10, font=font(13),
                         **kwargs)


def step_badge(master, text: str, done: bool = False) -> ctk.CTkLabel:
    fg, color = (CHIP_OK[0], OK_COLOR) if done else (BADGE_BG, TEAL)
    return ctk.CTkLabel(master, text="✓" if done else text, width=28, height=28, corner_radius=14,
                        fg_color=fg, text_color=color, font=font(14, "bold"))


def chip(master, text: str, colors) -> ctk.CTkLabel:
    fg, color = colors
    return ctk.CTkLabel(master, text=text, height=26, corner_radius=13, fg_color=fg, text_color=color,
                        font=font(12, "bold"), padx=10)


def _all_widgets(widget) -> list:
    """O widget e todos os seus descendentes (os do Tk, inclusive os internos do CustomTkinter)."""
    result = [widget]
    for child in tk.Misc.winfo_children(widget):
        result.extend(_all_widgets(child))
    return result


class IconView(ctk.CTkFrame):
    """Um ícone de app.ui.icons, nítido e com o fundo acompanhando o modo claro/escuro."""

    def __init__(self, master, name: str, size: int, bg):
        super().__init__(master, fg_color=bg, width=size, height=size, corner_radius=0)
        self._name, self._size, self._bg_color = name, size, bg
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0)
        self._render()

    def set_bg(self, bg) -> None:
        self._bg_color = bg
        self.configure(fg_color=bg)
        self._render()

    def _render(self) -> None:
        size = round(self._apply_widget_scaling(self._size))
        bg = self._apply_appearance_mode(self._bg_color)
        self.canvas.configure(width=size, height=size, bg=bg)
        icons.draw_icon(self.canvas, self._name, size, icons.palette(self._get_appearance_mode() == "dark"))

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "canvas"):
            self._render()


class Panel(ctk.CTkFrame):
    """Cartão branco (cinza no escuro) com borda fina e cabeçalho "número + título"."""

    def __init__(self, master, number: str, title: str, subtitle: str | None = None, done: bool = False):
        super().__init__(master, fg_color=PANEL, corner_radius=16, border_width=1, border_color=PANEL_BORDER)
        self.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        head.grid_columnconfigure(1, weight=1)
        self.badge = step_badge(head, number, done)
        self.badge.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 12))
        ctk.CTkLabel(head, text=title, height=22, font=font(16, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        if subtitle:
            ctk.CTkLabel(head, text=subtitle, height=16, font=font(12), text_color=MUTED_TEXT, anchor="w").grid(
                row=1, column=1, sticky="w")

    def set_done(self, done: bool, number: str) -> None:
        fg, color = (CHIP_OK[0], OK_COLOR) if done else (BADGE_BG, TEAL)
        self.badge.configure(text="✓" if done else number, fg_color=fg, text_color=color)


class DropZone(ctk.CTkFrame):
    """Área tracejada para arrastar a planilha ou clicar e escolher."""

    def __init__(self, master, on_file: Callable[[Path], None], on_click: Callable[[], None], dnd: bool):
        super().__init__(master, fg_color=PANEL, corner_radius=0)
        self.on_file, self.on_click, self.dnd = on_file, on_click, dnd
        self._hover = False

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

        self.icon = IconView(self, "upload", 84, ZONE_FILL)
        self.icon.place(relx=0.5, rely=0.5, y=-74, anchor="center")
        self.button = primary_button(self, text="Escolher arquivo…", width=180, bg_color=ZONE_FILL,
                                     command=self.on_click)
        self.button.place(relx=0.5, rely=0.5, y=58, anchor="center")

        for w in _all_widgets(self.canvas) + _all_widgets(self.icon):
            tk.Misc.bind(w, "<Button-1>", lambda _e: self.on_click(), add="+")
            tk.Misc.configure(w, cursor=_POINTER)
            tk.Misc.bind(w, "<Enter>", lambda _e: self._set_hover(True), add="+")
            tk.Misc.bind(w, "<Leave>", lambda _e: self.after(20, self._check_pointer), add="+")
        if dnd:
            for w in _all_widgets(self):
                w.drop_target_register("DND_Files")
                w.dnd_bind("<<DropEnter>>", self._on_enter)
                w.dnd_bind("<<DropLeave>>", self._on_leave)
                w.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------- desenho
    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20:
            return
        mode = self._apply_appearance_mode
        fill = mode(ZONE_HOVER if self._hover else ZONE_FILL)
        c.configure(bg=mode(PANEL))
        pts = [v for p in icons.rounded_rect(2, 2, w - 2, h - 2, 14) for v in p]
        if self._hover:
            c.create_polygon(pts, fill=fill, outline=mode(TEAL), width=2, joinstyle="round")
        else:
            c.create_polygon(pts, fill=fill, outline=mode(ZONE_BORDER), width=2, dash=(7, 5), joinstyle="round")

        cx, cy = w / 2, h / 2
        title = "Arraste a planilha para cá" if self.dnd else "Escolha a planilha preenchida"
        c.create_text(cx, cy - 8, text=title, font=font(18, "bold"), fill=mode(TEXT))
        c.create_text(cx, cy + 18, text="ou clique em qualquer lugar desta área" if self.dnd else
                      "clique em qualquer lugar desta área", font=font(12), fill=mode(MUTED_TEXT))
        c.create_text(cx, cy + 104, text="Excel (.xlsx) ou CSV  ·  uma pessoa por linha", font=font(11),
                      fill=mode(MUTED_TEXT))

    def _set_hover(self, on: bool) -> None:
        if on == self._hover:
            return
        self._hover = on
        bg = ZONE_HOVER if on else ZONE_FILL
        self.icon.set_bg(bg)
        self.button.configure(bg_color=bg)
        self._redraw()

    def _check_pointer(self) -> None:
        # <Leave> também chega ao passar de um widget interno para outro: só sai do hover fora da área.
        try:
            if not self.winfo_exists():
                return
            x, y = self.winfo_pointerxy()
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            if not (x0 <= x < x0 + self.winfo_width() and y0 <= y < y0 + self.winfo_height()):
                self._set_hover(False)
        except tk.TclError:
            pass

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "canvas"):
            self._redraw()

    # -------------------------------------------------------- arrastar e soltar
    def _on_enter(self, event):
        self._set_hover(True)
        return event.action

    def _on_leave(self, event):
        self._set_hover(False)
        return event.action

    def _on_drop(self, event):
        self._set_hover(False)
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        if paths:
            # Adia para fora do callback do arrastar (evita travar o Finder/Explorer com um diálogo aberto).
            self.after(10, lambda: self.on_file(paths[0]))
        return event.action


class ListWizard(ctk.CTkFrame):
    def __init__(self, master, on_exit: Callable[[], None], on_confirm: Callable[[Sheet], None],
                 initial: Sheet | None = None):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self.on_exit = on_exit
        self.on_confirm = on_confirm
        self.sheet: Sheet | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28)
        body.grid_columnconfigure(0, minsize=GUIDE_WIDTH)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_guide(body).grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.work = Panel(body, "2", "Carregue a planilha preenchida",
                          "Confira a prévia antes de confirmar")
        self.work.grid(row=0, column=1, sticky="nsew")
        self.work.grid_rowconfigure(1, weight=1)

        self._build_footer()

        self.content: ctk.CTkFrame | None = None
        if initial is not None:  # etapa já concluída: mostra a lista confirmada, que pode ser trocada
            self.sheet = initial
            self._show_loaded(initial)
        else:
            self._show_drop_zone()

    # ----------------------------------------------------------------- moldura
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 16))
        header.grid_columnconfigure(2, weight=1)
        ghost_button(header, text="‹  Menu", width=84, command=self.on_exit).grid(
            row=0, column=0, rowspan=2, sticky="w", padx=(0, 20))
        IconView(header, "list", 44, window_bg()).grid(row=0, column=1, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(header, text="Planilhar", font=font(24, "bold"), anchor="w").grid(
            row=0, column=2, sticky="sw")
        ctk.CTkLabel(header, text="Monte a lista de quem vai receber o certificado.", font=font(13),
                     text_color=MUTED_TEXT, anchor="w").grid(row=1, column=2, sticky="nw")

    def _build_footer(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color=PANEL_BORDER, corner_radius=0).grid(
            row=2, column=0, sticky="ew", pady=(18, 0))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=28, pady=14)
        footer.grid_columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(footer, text="●", font=font(12), text_color=MUTED_TEXT)
        self.status_dot.grid(row=0, column=0, padx=(0, 8))
        self.status = ctk.CTkLabel(footer, text="", anchor="w", text_color=MUTED_TEXT, font=font(13))
        self.status.grid(row=0, column=1, sticky="w")
        self.next_btn = primary_button(footer, text="Confirmar lista  ✓", width=180, state="disabled",
                                       command=self._confirm)
        self.next_btn.grid(row=0, column=2, sticky="e")

    def _set_status(self, text: str, color, ready: bool) -> None:
        self.status.configure(text=text, text_color=color)
        self.status_dot.configure(text_color=color)
        self.next_btn.configure(state="normal" if ready else "disabled")

    # ------------------------------------------------------------------- guia
    def _build_guide(self, master) -> Panel:
        panel = Panel(master, "1", "Baixe a planilha modelo", "Pronta para preencher")
        wrap = GUIDE_WIDTH - 40

        ctk.CTkLabel(panel, text="Cabeçalho já travado: preencha uma pessoa por linha e salve.", height=18, font=font(13), text_color=MUTED_TEXT, justify="left", anchor="w",
                     wraplength=wrap).grid(row=1, column=0, sticky="ew", padx=20, pady=(12, 12))

        ctk.CTkLabel(panel, text="COLUNAS OBRIGATÓRIAS", height=14, font=font(11, "bold"), text_color=MUTED_TEXT,
                     anchor="w").grid(row=2, column=0, sticky="w", padx=20, pady=(0, 6))
        cols = ctk.CTkFrame(panel, fg_color="transparent")
        cols.grid(row=3, column=0, sticky="ew", padx=20)
        cols.grid_columnconfigure(0, weight=1)
        for i, name in enumerate(TEMPLATE_COLUMNS):
            row = ctk.CTkFrame(cols, fg_color=ZONE_FILL, corner_radius=10)
            row.grid(row=i, column=0, sticky="ew", pady=(0, 6))
            ctk.CTkLabel(row, text=name, height=18, font=ctk.CTkFont(family="Menlo", size=13, weight="bold"),
                         text_color=TEAL, anchor="w").pack(fill="x", padx=12, pady=(6, 0))
            ctk.CTkLabel(row, text=COLUMN_HELP.get(name, ""), height=16, font=font(12), text_color=MUTED_TEXT,
                         anchor="w").pack(fill="x", padx=12, pady=(1, 6))

        ctk.CTkLabel(panel, text="COLUNAS EXTRAS", height=14, font=font(11, "bold"), text_color=MUTED_TEXT,
                     anchor="w").grid(row=4, column=0, sticky="w", padx=20, pady=(8, 4))
        ctk.CTkLabel(panel, text="Pode acrescentar outras (ex.: Curso, Data). Elas viram variáveis no "
                     "email, como {curso}.", height=16, font=font(12), text_color=MUTED_TEXT, justify="left",
                     anchor="w", wraplength=wrap).grid(row=5, column=0, sticky="ew", padx=20)

        panel.grid_rowconfigure(6, weight=1)
        primary_button(panel, text="⬇  Baixar modelo (.xlsx)", height=40,
                       command=self._download_template).grid(row=7, column=0, sticky="ew", padx=20, pady=(12, 18))
        return panel

    def _download_template(self) -> None:
        downloads = Path.home() / "Downloads"
        path = filedialog.asksaveasfilename(
            parent=self, title="Salvar planilha modelo", initialfile=TEMPLATE_FILENAME,
            initialdir=str(downloads if downloads.is_dir() else Path.home()),
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            saved = write_template(path)
        except OSError as exc:
            messagebox.showerror("Planilha modelo", f"Não foi possível salvar o arquivo:\n{exc}", parent=self)
            return
        if messagebox.askyesno("Planilha modelo", f"Modelo salvo em:\n{saved}\n\nAbrir agora?", parent=self):
            open_path(saved)

    # --------------------------------------------------------------- planilha
    def _replace_content(self) -> ctk.CTkFrame:
        if self.content is not None:
            self.content.destroy()
        self.content = ctk.CTkFrame(self.work, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(16, 20))
        self.content.grid_columnconfigure(0, weight=1)
        return self.content

    def _show_drop_zone(self) -> None:
        content = self._replace_content()
        content.grid_rowconfigure(0, weight=1)
        zone = DropZone(content, on_file=self._load, on_click=self._choose,
                        dnd=getattr(self.app, "dnd_available", False))
        zone.grid(row=0, column=0, sticky="nsew")
        self.sheet = None
        self.work.set_done(False, "2")
        self._set_status("Carregue a planilha preenchida para continuar.", MUTED_TEXT, ready=False)

    def _choose(self) -> None:
        downloads = Path.home() / "Downloads"
        path = filedialog.askopenfilename(
            parent=self, title="Escolha a planilha preenchida",
            initialdir=str(downloads if downloads.is_dir() else Path.home()),
            filetypes=[("Planilhas", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        if path.is_dir() or path.suffix.lower() not in SHEET_SUFFIXES:
            messagebox.showerror("Planilha", "Use uma planilha .xlsx ou .csv.", parent=self)
            return
        try:
            sheet = read_sheet(path)
        except SpreadsheetError as exc:
            messagebox.showerror("Planilha", str(exc), parent=self)
            return
        self.sheet = sheet
        self._show_loaded(sheet)

    def _show_loaded(self, sheet: Sheet) -> None:
        content = self._replace_content()
        missing = missing_columns(sheet.headers)
        count = len(sheet.rows)

        # arquivo: selo do tipo, nome, contagem e "Trocar"
        top = ctk.CTkFrame(content, fg_color=ZONE_FILL, corner_radius=12)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        kind = sheet.path.suffix.lstrip(".").upper()[:4] or "?"
        ctk.CTkLabel(top, text=kind, width=52, height=52, corner_radius=12, fg_color=BTN, text_color="white",
                     font=font(13, "bold")).grid(row=0, column=0, rowspan=2, padx=14, pady=14)
        ctk.CTkLabel(top, text=sheet.path.name, font=font(15, "bold"), anchor="w").grid(
            row=0, column=1, sticky="sw", pady=(14, 0))
        people = f"{count} pessoa" + ("" if count == 1 else "s")
        columns = f"{len(sheet.headers)} coluna" + ("" if len(sheet.headers) == 1 else "s")
        ctk.CTkLabel(top, text=f"{people}  ·  {columns}", font=font(12), text_color=MUTED_TEXT, anchor="w").grid(
            row=1, column=1, sticky="nw", pady=(0, 14))
        ghost_button(top, text="Trocar planilha", width=130, command=self._show_drop_zone).grid(
            row=0, column=2, rowspan=2, padx=14)

        # colunas: obrigatórias (ok/faltando) e extras
        chips = ctk.CTkFrame(content, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        required = set(TEMPLATE_COLUMNS)
        extras = [h for h in sheet.headers if variable_key(h) not in required]
        items = [(f"✓ {c}", CHIP_OK) for c in TEMPLATE_COLUMNS if c not in missing]
        items += [(f"✕ {c}", CHIP_MISSING) for c in missing]
        items += [(h, CHIP_EXTRA) for h in extras]
        if len(items) > MAX_CHIPS:
            items = items[:MAX_CHIPS - 1] + [(f"+{len(items) - MAX_CHIPS + 1}", CHIP_EXTRA)]
        for text, colors in items:
            chip(chips, text, colors).pack(side="left", padx=(0, 6))

        row = 2
        if missing:
            alert = ctk.CTkFrame(content, fg_color=ALERT_BG, corner_radius=10)
            alert.grid(row=row, column=0, sticky="ew", pady=(12, 0))
            ctk.CTkLabel(alert, text=f"Faltam as colunas {', '.join(missing)}. Baixe a planilha modelo ao lado "
                         "e copie os dados para ela.", text_color=ERROR_COLOR, font=font(13), anchor="w",
                         justify="left", wraplength=520).pack(fill="x", padx=14, pady=10)
            row += 1

        # prévia
        content.grid_rowconfigure(row, weight=1)
        columns_def = [("_line", "Linha", 60)] + [(f"c{i}", h, 180) for i, h in enumerate(sheet.headers)]
        table = Table(content, columns_def, height=6)
        table.grid(row=row, column=0, sticky="nsew", pady=(14, 0))
        table.tree.column("_line", width=60, stretch=False)
        rows = [((line, *(r[h] for h in sheet.headers)), None)
                for line, r in zip(sheet.line_numbers[:PREVIEW_ROWS], sheet.rows[:PREVIEW_ROWS])]
        table.set_rows(rows)

        if missing:
            self.work.set_done(False, "2")
            self._set_status(f"Faltam as colunas: {', '.join(missing)}.", ERROR_COLOR, ready=False)
            return
        self.work.set_done(True, "2")
        extra = f" Prévia das primeiras {PREVIEW_ROWS} linhas." if count > PREVIEW_ROWS else ""
        self._set_status(f"Tudo certo: {people} na lista.{extra} Confira e confirme.", OK_COLOR, ready=True)

    def _confirm(self) -> None:
        if self.sheet is not None and not missing_columns(self.sheet.headers):
            self.on_confirm(self.sheet)
