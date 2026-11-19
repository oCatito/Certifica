"""Fluxo "Enviar": Arquivos → Pré-verificação → Revisão → Envio → Concluído."""

from __future__ import annotations

import copy
import html
import queue
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from app.core.campaign import RESULT_FAILED, RESULT_PENDING, RESULT_SENT, Campaign, DailyCounter
from app.core.config import MODE_HTML, AppConfig, get_password
from app.core.mailer import recipient_variables, render_for, send_test
from app.core.matcher import ColumnMapping, Recipient, Status, check_recipients
from app.core.sender import FinishedEvent, LogEvent, PausedEvent, ProgressEvent, SendJob, WaitEvent
from app.core.spreadsheet import Sheet, SpreadsheetError, read_sheet, suggest_columns
from app.core.templates import unknown_variables
from app.core.text import variable_key
from app.paths import config_dir, open_path
from app.ui.widgets import (
    ACCENT,
    ERROR_COLOR,
    MUTED_TEXT,
    OK_COLOR,
    WARN_COLOR,
    Card,
    CountdownRing,
    LogBox,
    Table,
    font,
    run_in_background,
    set_readonly_text,
)

STEPS = ["Arquivos", "Pré-verificação", "Revisão", "Envio", "Concluído"]
NOT_SELECTED = "— escolha a coluna —"


def secondary_button(master, **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(master, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), **kwargs)


def human_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "menos de 1 minuto"
    if minutes < 60:
        return f"cerca de {minutes} min"
    return f"cerca de {minutes // 60} h {minutes % 60:02d} min"


class SendWizard(ctk.CTkFrame):
    def __init__(self, master, on_exit: Callable[[], None]):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self.on_exit = on_exit

        # estado do fluxo
        # Se a etapa 1 foi concluída, já começa com a lista confirmada (pode trocar).
        self.sheet: Sheet | None = getattr(master, "list_sheet", None)
        self.folder: Path | None = None
        self.mapping: ColumnMapping | None = None
        self.recipients: list[Recipient] = []
        self.to_send: list[Recipient] = []
        self.preview_index = 0
        self.job: SendJob | None = None
        self.events: queue.Queue = queue.Queue()
        self.finished: FinishedEvent | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self.body: ctk.CTkFrame | None = None
        self.footer: ctk.CTkFrame | None = None
        self.show_files()

    @property
    def cfg(self) -> AppConfig:
        return self.app.config_data

    @property
    def is_sending(self) -> bool:
        return self.job is not None and self.job.is_alive()

    def stop_sending(self) -> None:
        if self.job is not None:
            self.job.cancel()
            self.job.join(timeout=5)

    # ------------------------------------------------------------------ layout
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        header.grid_columnconfigure(1, weight=1)
        self.back_btn = secondary_button(header, text="← Menu", width=90, command=self._exit)
        self.back_btn.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Enviar", font=font(22, "bold")).grid(row=0, column=1, sticky="w", padx=16)

        steps = ctk.CTkFrame(header, fg_color="transparent")
        steps.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.step_labels = []
        for i, name in enumerate(STEPS):
            lbl = ctk.CTkLabel(steps, text=f"{i + 1}. {name}", corner_radius=12, padx=10, font=font(13))
            lbl.pack(side="left", padx=(0, 6))
            self.step_labels.append(lbl)

    def _set_step(self, index: int) -> ctk.CTkFrame:
        for i, lbl in enumerate(self.step_labels):
            if i == index:
                lbl.configure(fg_color=ACCENT, text_color="white", font=font(13, "bold"))
            else:
                lbl.configure(fg_color="transparent", text_color=MUTED_TEXT if i > index else ("gray20", "gray80"),
                              font=font(13))
        for w in (self.body, self.footer):
            if w is not None:
                w.destroy()
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=24)
        self.body.grid_columnconfigure(0, weight=1)
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=2, column=0, sticky="ew", padx=24, pady=16)
        self.back_btn.configure(state="normal")
        return self.body

    def _exit(self) -> None:
        if self.is_sending:
            return
        self.on_exit()

    # ------------------------------------------------------------ 1. Arquivos
    def show_files(self) -> None:
        body = self._set_step(0)

        card = Card(body, "Planilha com a lista de pessoas (.xlsx ou .csv)")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.sheet_entry = ctk.CTkEntry(card, placeholder_text="Nenhuma planilha escolhida")
        self.sheet_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(4, 4))
        ctk.CTkButton(card, text="Escolher planilha…", width=160, command=self._choose_sheet).grid(
            row=1, column=1, padx=(0, 16), pady=(4, 4))
        self.sheet_info = ctk.CTkLabel(card, text="", anchor="w", justify="left", text_color=MUTED_TEXT, font=font(12))
        self.sheet_info.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

        card = Card(body, "Pasta com os certificados (PDF)")
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.folder_entry = ctk.CTkEntry(card, placeholder_text="Nenhuma pasta escolhida")
        self.folder_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(4, 4))
        ctk.CTkButton(card, text="Escolher pasta…", width=160, command=self._choose_folder).grid(
            row=1, column=1, padx=(0, 16), pady=(4, 4))
        self.folder_info = ctk.CTkLabel(card, text="", anchor="w", text_color=MUTED_TEXT, font=font(12))
        self.folder_info.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

        card = Card(body, "Quais colunas da planilha são…")
        card.grid(row=2, column=0, sticky="ew")
        self.column_menus: dict[str, ctk.CTkOptionMenu] = {}
        for i, (role, label) in enumerate((("name", "Nome da pessoa"), ("email", "Email"),
                                           ("file", "Nome do arquivo do certificado"))):
            ctk.CTkLabel(card, text=label, anchor="w").grid(row=i + 1, column=0, sticky="w", padx=16, pady=4)
            menu = ctk.CTkOptionMenu(card, values=[NOT_SELECTED], width=280, command=lambda _v: self._validate_files(),
                                     dynamic_resizing=False)
            menu.grid(row=i + 1, column=1, sticky="e", padx=16, pady=4)
            self.column_menus[role] = menu
        self.vars_info = ctk.CTkLabel(card, text="", anchor="w", justify="left", text_color=MUTED_TEXT,
                                      font=font(12), wraplength=760)
        self.vars_info.grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 12))

        self.files_error = ctk.CTkLabel(self.footer, text="", text_color=ERROR_COLOR, anchor="w")
        self.files_error.pack(side="left")
        self.next_btn = ctk.CTkButton(self.footer, text="Próximo →", width=140, command=self.show_check)
        self.next_btn.pack(side="right")

        # Ao voltar para esta etapa, restaura o que já foi escolhido.
        if self.sheet is not None:
            self._apply_sheet(self.sheet, keep_mapping=True)
        if self.folder is not None:
            self._apply_folder(self.folder)
        self._validate_files()

    def _choose_sheet(self) -> None:
        initial = str(self.sheet.path.parent) if self.sheet else None
        path = filedialog.askopenfilename(
            parent=self, title="Escolha a planilha", initialdir=initial,
            filetypes=[("Planilhas", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            sheet = read_sheet(path)
        except SpreadsheetError as exc:
            messagebox.showerror("Planilha", str(exc), parent=self)
            return
        self.sheet = sheet
        self._apply_sheet(sheet, keep_mapping=False)
        # Sugere a pasta "certificados" ao lado da planilha, se existir.
        if self.folder is None:
            for name in ("certificados", "Certificados", "CERTIFICADOS"):
                candidate = sheet.path.parent / name
                if candidate.is_dir():
                    self._apply_folder(candidate)
                    break
        self._validate_files()

    def _apply_sheet(self, sheet: Sheet, keep_mapping: bool) -> None:
        self.sheet_entry.configure(state="normal")
        self.sheet_entry.delete(0, "end")
        self.sheet_entry.insert(0, str(sheet.path))
        self.sheet_entry.configure(state="disabled")
        self.sheet_info.configure(text=f"{len(sheet.rows)} linha(s) · colunas: {', '.join(sheet.headers)}")
        suggestions = suggest_columns(sheet.headers)
        current = {"name": self.mapping.name, "email": self.mapping.email, "file": self.mapping.file} \
            if keep_mapping and self.mapping else {}
        for role, menu in self.column_menus.items():
            menu.configure(values=[NOT_SELECTED] + sheet.headers)
            value = current.get(role) or suggestions.get(role)
            menu.set(value if value in sheet.headers else NOT_SELECTED)

    def _choose_folder(self) -> None:
        initial = str(self.folder or (self.sheet.path.parent if self.sheet else "")) or None
        path = filedialog.askdirectory(parent=self, title="Escolha a pasta dos certificados", initialdir=initial)
        if path:
            self._apply_folder(Path(path))
            self._validate_files()

    def _apply_folder(self, folder: Path) -> None:
        self.folder = folder
        self.folder_entry.configure(state="normal")
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, str(folder))
        self.folder_entry.configure(state="disabled")
        try:
            pdfs = sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
            self.folder_info.configure(text=f"{pdfs} arquivo(s) PDF na pasta")
        except OSError as exc:
            self.folder_info.configure(text=f"Não foi possível ler a pasta: {exc}")

    def _validate_files(self) -> None:
        error = ""
        values = {role: menu.get() for role, menu in self.column_menus.items()}
        if self.sheet is None:
            error = "Escolha a planilha."
        elif self.folder is None:
            error = "Escolha a pasta dos certificados."
        elif NOT_SELECTED in values.values():
            error = "Escolha as colunas de nome, email e arquivo."
        elif len(set(values.values())) < 3:
            error = "Nome, email e arquivo precisam ser colunas diferentes."
        if self.sheet is not None and NOT_SELECTED not in values.values():
            others = [h for h in self.sheet.headers if h not in values.values()]
            extra = ", ".join("{" + variable_key(h) + "}" for h in others)
            self.vars_info.configure(text=f"Outras colunas viram variáveis para o email: {extra}" if extra else "")
        self.files_error.configure(text=error)
        self.next_btn.configure(state="disabled" if error else "normal")
        if not error:
            self.mapping = ColumnMapping(name=values["name"], email=values["email"], file=values["file"])

    # ------------------------------------------------------ 2. Pré-verificação
    def show_check(self) -> None:
        assert self.sheet and self.folder and self.mapping
        try:
            # Relê a planilha (pode ter sido corrigida enquanto o programa estava aberto).
            self.sheet = read_sheet(self.sheet.path)
            campaign = Campaign(self.sheet.path)
            self.recipients = check_recipients(self.sheet, self.mapping, self.folder, campaign.sent_keys)
        except (SpreadsheetError, OSError) as exc:
            messagebox.showerror("Pré-verificação", str(exc), parent=self)
            return
        self.to_send = [r for r in self.recipients if r.status is Status.OK]

        body = self._set_step(1)
        body.grid_rowconfigure(2, weight=1)

        counts = {s: sum(r.status is s for r in self.recipients) for s in Status}
        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.grid(row=0, column=0, sticky="w")
        colors = {Status.OK: OK_COLOR, Status.FILE_NOT_FOUND: ERROR_COLOR, Status.INVALID_EMAIL: ERROR_COLOR,
                  Status.DUPLICATE_EMAIL: WARN_COLOR, Status.ALREADY_SENT: MUTED_TEXT}
        for status in Status:
            ctk.CTkLabel(chips, text=f"{status.value}: {counts[status]}", text_color=colors[status],
                         font=font(14, "bold")).pack(side="left", padx=(0, 20))

        filter_row = ctk.CTkFrame(body, fg_color="transparent")
        filter_row.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        ctk.CTkLabel(filter_row, text="Mostrar:").pack(side="left")
        self.filter_switch = ctk.CTkSegmentedButton(filter_row, values=["Todos", "Somente problemas"],
                                                    command=lambda _v: self._fill_check_table())
        self.filter_switch.set("Somente problemas" if any(r.status.is_problem for r in self.recipients) else "Todos")
        self.filter_switch.pack(side="left", padx=8)

        self.check_table = Table(body, [
            ("linha", "Linha", 60), ("nome", "Nome", 200), ("email", "Email", 220),
            ("arquivo", "Arquivo", 210), ("status", "Status", 180), ("detalhe", "Detalhe", 260),
        ])
        self.check_table.grid(row=2, column=0, sticky="nsew")
        self._fill_check_table()

        secondary_button(self.footer, text="← Voltar", width=110, command=self.show_files).pack(side="left")
        n = len(self.to_send)
        if n == 0:
            msg = "Todas as pessoas desta lista já receberam." if counts[Status.ALREADY_SENT] == len(self.recipients) \
                else "Nenhuma linha está pronta para envio. Corrija a planilha/pasta e volte."
            ctk.CTkLabel(self.footer, text=msg, text_color=WARN_COLOR).pack(side="left", padx=16)
        secondary_button(self.footer, text="↻ Verificar de novo", width=150, command=self.show_check).pack(
            side="left", padx=8)
        ctk.CTkButton(self.footer, text=f"Próximo → ({n} para enviar)", width=200,
                      state="normal" if n else "disabled", command=self.show_review).pack(side="right")

    def _fill_check_table(self) -> None:
        only_problems = self.filter_switch.get() == "Somente problemas"
        tags = {Status.FILE_NOT_FOUND: "error", Status.INVALID_EMAIL: "error",
                Status.DUPLICATE_EMAIL: "warn", Status.ALREADY_SENT: "muted"}
        rows = [
            ((r.line, r.name, r.email, r.filename, r.status.value, r.detail), tags.get(r.status))
            for r in self.recipients
            if not only_problems or r.status.is_problem
        ]
        self.check_table.set_rows(rows)

    # ------------------------------------------------------------- 3. Revisão
    def show_review(self) -> None:
        body = self._set_step(2)
        body.grid_rowconfigure(2, weight=1)
        self.preview_index = min(self.preview_index, len(self.to_send) - 1)

        nav = ctk.CTkFrame(body, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew")
        secondary_button(nav, text="◀", width=40, command=lambda: self._move_preview(-1)).pack(side="left")
        self.nav_label = ctk.CTkLabel(nav, text="", font=font(14, "bold"))
        self.nav_label.pack(side="left", padx=12)
        secondary_button(nav, text="▶", width=40, command=lambda: self._move_preview(1)).pack(side="left")
        if self.cfg.message.mode == MODE_HTML:
            secondary_button(nav, text="Abrir prévia HTML no navegador", width=230,
                             command=self._open_html_preview).pack(side="right")

        self.headers_card = Card(body)
        self.headers_card.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        self.header_values: dict[str, ctk.CTkLabel] = {}
        for i, key in enumerate(("De", "Para", "Responder para", "Assunto", "Anexo")):
            ctk.CTkLabel(self.headers_card, text=key, text_color=MUTED_TEXT, anchor="w", width=120).grid(
                row=i, column=0, sticky="w", padx=(16, 8), pady=(8 if i == 0 else 0, 8 if i == 4 else 0))
            val = ctk.CTkLabel(self.headers_card, text="", anchor="w", justify="left", wraplength=700)
            val.grid(row=i, column=1, sticky="w", pady=(8 if i == 0 else 0, 8 if i == 4 else 0))
            self.header_values[key] = val
        self.headers_card.grid_columnconfigure(1, weight=1)

        self.preview_box = ctk.CTkTextbox(body, wrap="word")
        self.preview_box.grid(row=2, column=0, sticky="nsew")
        self.preview_warning = ctk.CTkLabel(body, text="", text_color=WARN_COLOR, anchor="w", justify="left",
                                            wraplength=900)
        self.preview_warning.grid(row=3, column=0, sticky="w", pady=(6, 0))

        counter = DailyCounter(self.cfg.smtp.sender_address)
        used, limit = counter.count(), self.cfg.sending.daily_limit
        remaining = max(0, limit - used)
        n = len(self.to_send)
        now_n = min(n, remaining)
        eta = human_duration(now_n * (self.cfg.sending.average_interval + 1.0))
        summary = f"Serão enviados {n} email(s). Nas últimas 24h esta conta enviou {used} de {limit} (limite diário)."
        if remaining == 0:
            summary += " O limite já foi atingido: tente novamente mais tarde."
        elif n > remaining:
            summary += (f" Agora dá para enviar {remaining}; os outros {n - remaining} ficarão pendentes "
                        "para continuar depois.")
        summary += f" Tempo estimado: {eta}" + (" (em média, pelo intervalo aleatório)." if self.cfg.sending.random_interval else ".")
        ctk.CTkLabel(body, text=summary, anchor="w", justify="left", wraplength=900, font=font(13)).grid(
            row=4, column=0, sticky="w", pady=(8, 0))

        secondary_button(self.footer, text="← Voltar", width=110, command=self.show_check).pack(side="left")
        self.test_btn = secondary_button(self.footer, text="✉ Enviar teste para mim", width=190,
                                         command=self._send_test)
        self.test_btn.pack(side="left", padx=8)
        ctk.CTkButton(self.footer, text="Iniciar envio", width=160, state="normal" if remaining else "disabled",
                      font=font(14, "bold"), command=self._confirm_start).pack(side="right")
        self._render_preview()

    def _move_preview(self, delta: int) -> None:
        self.preview_index = (self.preview_index + delta) % len(self.to_send)
        self._render_preview()

    def _render_preview(self) -> None:
        rec = self.to_send[self.preview_index]
        cfg = self.cfg
        self.nav_label.configure(text=f"Pessoa {self.preview_index + 1} de {len(self.to_send)} — {rec.name or rec.email}")
        subject, text_body, html_body = render_for(cfg, rec)
        sender = cfg.smtp.sender_address
        self.header_values["De"].configure(
            text=f"{cfg.sender.display_name} <{sender}>" if cfg.sender.display_name else sender)
        self.header_values["Para"].configure(text=f"{rec.name} <{rec.email}>" if rec.name else rec.email)
        self.header_values["Responder para"].configure(text=cfg.sender.reply_to or "—")
        self.header_values["Assunto"].configure(text=subject)
        size_kb = rec.file_path.stat().st_size / 1024 if rec.file_path and rec.file_path.exists() else 0
        self.header_values["Anexo"].configure(text=f"📎 {rec.file_path.name if rec.file_path else '?'} ({size_kb:,.0f} KB)")
        text = text_body
        if html_body is not None:
            text = "[Modelo HTML — abaixo, a versão em texto. Use “Abrir prévia HTML no navegador” para ver a formatação.]\n\n" + text
        set_readonly_text(self.preview_box, text)
        template = cfg.message.subject + (cfg.message.html_body if html_body is not None else cfg.message.text_body)
        missing = unknown_variables(template, recipient_variables(rec))
        self.preview_warning.configure(
            text=f"⚠ Variáveis sem coluna correspondente na planilha (vão aparecer como estão): {', '.join(missing)}"
            if missing else "")

    def _open_html_preview(self) -> None:
        rec = self.to_send[self.preview_index]
        subject, _text, html_body = render_for(self.cfg, rec)
        path = config_dir() / "previa_email.html"
        safe = html.escape(subject)
        path.write_text(f"<!doctype html><meta charset='utf-8'><title>{safe}</title>"
                        f"<p style='font:13px sans-serif;color:#666'>Assunto: <b>{safe}</b></p><hr>{html_body}",
                        encoding="utf-8")
        webbrowser.open(path.as_uri())

    def _password(self) -> str | None:
        return get_password(self.cfg.smtp.username) if self.cfg.smtp.auth else None

    def _send_test(self) -> None:
        rec = self.to_send[self.preview_index]
        cfg = copy.deepcopy(self.cfg)
        password = self._password()
        self.test_btn.configure(state="disabled", text="Enviando teste…")

        def done(result, exc):
            if not self.test_btn.winfo_exists():
                return
            self.test_btn.configure(state="normal", text="✉ Enviar teste para mim")
            ok, message = result if exc is None else (False, str(exc))
            if ok:
                DailyCounter(cfg.smtp.sender_address).record()
                messagebox.showinfo("Envio de teste", message, parent=self)
            else:
                messagebox.showerror("Envio de teste", message, parent=self)

        run_in_background(self, lambda: send_test(cfg, password, rec), done)

    def _confirm_start(self) -> None:
        n = len(self.to_send)
        if not messagebox.askyesno(
            "Iniciar envio",
            f"Enviar {n} email(s) com certificado agora?\n\nVocê poderá pausar ou cancelar durante o envio.",
            parent=self,
        ):
            return
        self.start_sending(self.to_send)

    # --------------------------------------------------------------- 4. Envio
    def start_sending(self, recipients: list[Recipient]) -> None:
        assert self.sheet is not None
        cfg = copy.deepcopy(self.cfg)
        self.events = queue.Queue()
        self.finished = None
        self.job = SendJob(
            cfg, self._password(), recipients, Campaign(self.sheet.path), DailyCounter(cfg.smtp.sender_address), self.events
        )

        body = self._set_step(3)
        self.back_btn.configure(state="disabled")
        body.grid_rowconfigure(4, weight=1)

        self.send_status = ctk.CTkLabel(body, text="Enviando…", font=font(18, "bold"), anchor="w")
        self.send_status.grid(row=0, column=0, sticky="w")
        self.progress = ctk.CTkProgressBar(body, height=16)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        self.progress_label = ctk.CTkLabel(body, text=f"0 de {len(recipients)}", anchor="w")
        self.progress_label.grid(row=2, column=0, sticky="w")
        self.quota_label = ctk.CTkLabel(body, text="", anchor="w", text_color=MUTED_TEXT, font=font(12))
        self.quota_label.grid(row=3, column=0, sticky="w", pady=(0, 8))
        # Timer da pausa até o próximo envio (fica vazio enquanto envia)
        self.wait_ring = CountdownRing(body, size=120, thickness=9, caption="próximo envio")
        self.wait_ring.grid(row=0, column=1, rowspan=4, sticky="ne", padx=(16, 0))
        self.log = LogBox(body)
        self.log.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

        self.pause_btn = secondary_button(self.footer, text="⏸ Pausar", width=130, command=self._toggle_pause)
        self.pause_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(self.footer, text="Cancelar envio", width=150, fg_color=("#b3261e", "#9b2c26"),
                                        hover_color=("#8c1d17", "#7a221d"), command=self._cancel)
        self.cancel_btn.pack(side="right")

        self.job.start()
        self.after(100, self._poll_events)

    def _toggle_pause(self) -> None:
        if not self.job:
            return
        if self.job.paused:
            self.job.resume()
        else:
            self.job.pause()

    def _cancel(self) -> None:
        if self.job and messagebox.askyesno(
            "Cancelar envio", "Parar o envio? Quem já recebeu fica registrado; os demais ficam pendentes.", parent=self
        ):
            self.cancel_btn.configure(state="disabled", text="Cancelando…")
            self.pause_btn.configure(state="disabled")
            self.job.cancel()

    def _poll_events(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                event = self.events.get_nowait()
                if isinstance(event, LogEvent):
                    self.log.append(event.text, event.level)
                elif isinstance(event, ProgressEvent):
                    self.progress.set(event.done / event.total if event.total else 1)
                    self.progress_label.configure(
                        text=f"{event.done} de {event.total} processados  ·  {event.sent} enviados  ·  "
                             f"{event.failed} falhas")
                    self.quota_label.configure(
                        text=f"Limite diário da conta: {event.quota_used} de {event.quota_limit} nas últimas 24h")
                elif isinstance(event, WaitEvent):
                    if event.seconds >= 1:
                        self.wait_ring.start(event.seconds)
                elif isinstance(event, PausedEvent):
                    self.send_status.configure(text="Pausado" if event.paused else "Enviando…")
                    self.pause_btn.configure(text="▶ Continuar" if event.paused else "⏸ Pausar")
                elif isinstance(event, FinishedEvent):
                    self.finished = event
                    self.show_done()
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    # ------------------------------------------------------------ 5. Concluído
    def show_done(self) -> None:
        done = self.finished
        assert done is not None
        body = self._set_step(4)
        body.grid_rowconfigure(3, weight=1)

        sent, failed, pending = done.counts[RESULT_SENT], done.counts[RESULT_FAILED], done.counts[RESULT_PENDING]
        title = "Envio concluído!" if not done.stop_reason and not failed else "Envio finalizado"
        ctk.CTkLabel(body, text=title, font=font(22, "bold"), anchor="w").grid(row=0, column=0, sticky="w")

        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="w", pady=(8, 4))
        for text, color in ((f"✔ {sent} enviados", OK_COLOR), (f"✖ {failed} falhas", ERROR_COLOR),
                            (f"⏸ {pending} pendentes", WARN_COLOR)):
            ctk.CTkLabel(chips, text=text, text_color=color, font=font(16, "bold")).pack(side="left", padx=(0, 24))

        info = []
        if done.stop_reason:
            info.append(done.stop_reason)
        if pending and "Limite" not in done.stop_reason:
            info.append("Para enviar os pendentes, abra a mesma planilha de novo: quem já recebeu será pulado.")
        if done.report_path:
            info.append(f"Relatório: {done.report_path}")
        ctk.CTkLabel(body, text="\n".join(info), anchor="w", justify="left", wraplength=900).grid(
            row=2, column=0, sticky="w", pady=(4, 8))

        problems = [r for r in done.results if r.status != RESULT_SENT]
        if problems:
            table = Table(body, [("linha", "Linha", 60), ("nome", "Nome", 200), ("email", "Email", 220),
                                 ("status", "Status", 100), ("erro", "Erro", 420)])
            table.grid(row=3, column=0, sticky="nsew")
            table.set_rows([((r.recipient.line, r.recipient.name, r.recipient.email, r.status, r.error),
                             "error" if r.status == RESULT_FAILED else "warn") for r in problems])

        secondary_button(self.footer, text="Voltar ao menu", width=140, command=self.on_exit).pack(side="left")
        if done.report_path:
            report = done.report_path
            secondary_button(self.footer, text="Abrir relatório", width=140,
                             command=lambda: open_path(report)).pack(side="left", padx=8)
            secondary_button(self.footer, text="Abrir pasta", width=120,
                             command=lambda: open_path(report.parent)).pack(side="left")
        if failed:
            ctk.CTkButton(self.footer, text=f"Reenviar falhas ({failed})", width=180,
                          command=self._retry_failed).pack(side="right")

    def _retry_failed(self) -> None:
        assert self.finished is not None
        failed = [r.recipient for r in self.finished.results if r.status == RESULT_FAILED]
        if failed and messagebox.askyesno("Reenviar falhas", f"Tentar enviar de novo para {len(failed)} pessoa(s)?",
                                          parent=self):
            self.start_sending(failed)
