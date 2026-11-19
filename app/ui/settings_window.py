"""Página de configurações (engrenagem), exibida dentro da janela principal."""

from __future__ import annotations

import copy
import html
import webbrowser
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from app.core.config import (
    DEFAULT_HTML_BODY,
    DEFAULT_TEXT_BODY,
    MODE_HTML,
    MODE_TEXT,
    SECURITY_NONE,
    SECURITY_SSL,
    SECURITY_STARTTLS,
    PROVIDER_CUSTOM,
    SMTP_PROVIDERS,
    AppConfig,
    get_password,
    save_config,
    set_password,
)
from app.core.mailer import test_connection
from app.core.matcher import is_valid_email
from app.core.templates import build_variables, html_to_text, render, unknown_variables
from app import APP_TITLE, __version__
from app.paths import config_dir, resource_path
from app.ui.widgets import CARD_COLOR, ERROR_COLOR, MUTED_TEXT, OK_COLOR, font, run_in_background, set_readonly_text

SECURITY_LABELS = {
    SECURITY_STARTTLS: "STARTTLS (geralmente porta 587)",
    SECURITY_SSL: "SSL/TLS (geralmente porta 465)",
    SECURITY_NONE: "Nenhuma — sem criptografia (porta 25, rede interna)",
}
MODE_LABELS = {MODE_TEXT: "Texto editável", MODE_HTML: "HTML formatado"}
INTERVAL_MODES = {"fixed": "Fixo", "random": "Aleatório"}
TIME_UNITS = {"segundos": 1, "minutos": 60}
MAX_INTERVAL_SECONDS = 60 * 60

GITHUB_URL = "https://github.com/ocatito"
# Logo do autor na aba "Sobre": uma versão para o tema claro e outra para o escuro.
AUTHOR_LOGO = ("assets/author_logo_light.png", "assets/author_logo_dark.png")
ABOUT_TEXT = (
    "O Certifica envia certificados em PDF por email, cada um para a sua pessoa, a partir de uma "
    "planilha. Ele encontra o arquivo de cada participante, personaliza o assunto e a mensagem com "
    "os dados da planilha e envia tudo com intervalo e limite diário, sem repetir quem já recebeu."
)

SAMPLE_NAME = "Marina Silva de Souza"
SAMPLE_EMAIL = "marina@exemplo.com"
SAMPLE_FILE = "marina_silva_de_souza.pdf"
SAMPLE_VARIABLES = build_variables(
    {"curso": "Curso de Exemplo", "data": "12/11/2026"}, name=SAMPLE_NAME, email=SAMPLE_EMAIL, filename=SAMPLE_FILE,
)

# Cores do “papel” do email na prévia (claro, escuro).
EMAIL_BG = ("white", "gray14")
EMAIL_TEXT = ("gray10", "gray92")
EMAIL_MUTED = ("gray40", "gray62")
EMAIL_RULE = ("gray85", "gray25")
EMAIL_CHIP = ("gray90", "gray22")


class SettingsPage(ctk.CTkFrame):
    """Configurações exibidas dentro da janela principal (troca a visualização, sem abrir outra janela)."""

    def __init__(self, master, cfg: AppConfig, on_saved: Callable[[AppConfig], None], on_exit: Callable[[], None]):
        super().__init__(master, fg_color="transparent")
        self.cfg = copy.deepcopy(cfg)
        self.on_saved = on_saved
        self.on_exit = on_exit
        self.saved_password = get_password(self.cfg.smtp.username)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))
        ctk.CTkButton(
            header, text="← Menu", width=90, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.on_exit,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Configurações", font=font(22, "bold")).grid(row=0, column=1, sticky="w", padx=16)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 0))
        for name in ("Servidor", "Remetente", "Mensagem", "Envio", "Sobre"):
            self.tabs.add(name)
        self._build_server(self.tabs.tab("Servidor"))
        self._build_sender(self.tabs.tab("Remetente"))
        self._build_message(self.tabs.tab("Mensagem"))
        self._build_sending(self.tabs.tab("Envio"))
        self._build_about(self.tabs.tab("Sobre"))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=16)
        ctk.CTkButton(footer, text="Salvar", width=120, command=self.save).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancelar", width=120, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.on_exit,
        ).pack(side="right", padx=8)

    # --- helpers de layout ---
    @staticmethod
    def _row(parent, row: int, label: str, widget, hint: str | None = None) -> ctk.CTkLabel:
        """Coloca rótulo + campo; devolve o rótulo de dica (abaixo do campo) para poder ser alterado depois."""
        title = ctk.CTkLabel(parent, text=label, anchor="w")
        title.grid(row=row, column=0, sticky="w", padx=(4, 12), pady=(10, 0))
        widget.grid(row=row, column=1, sticky="ew", pady=(10, 0))
        hint_label = ctk.CTkLabel(parent, text=hint or "", anchor="w", justify="left", text_color=MUTED_TEXT,
                                  font=font(12), wraplength=520)
        if hint:
            hint_label.grid(row=row + 1, column=1, sticky="w", pady=(2, 0))
        hint_label.title = title  # type: ignore[attr-defined]
        return hint_label

    @staticmethod
    def _set_hint(hint_label: ctk.CTkLabel, text: str) -> None:
        hint_label.configure(text=text)
        if text:
            hint_label.grid()
        else:
            hint_label.grid_remove()

    # --- Servidor ---
    def _build_server(self, tab) -> None:
        tab.grid_columnconfigure(1, weight=1)
        s = self.cfg.smtp
        self.provider_key = s.provider if s.provider in SMTP_PROVIDERS else PROVIDER_CUSTOM

        self.provider_menu = ctk.CTkOptionMenu(
            tab, values=[p.label for p in SMTP_PROVIDERS.values()], command=self._on_provider)
        self.provider_menu.set(SMTP_PROVIDERS[self.provider_key].label)
        self._row(tab, 0, "Provedor", self.provider_menu,
                  "Escolha o seu provedor para preencher servidor, porta e segurança automaticamente, "
                  "ou “Outro servidor” para qualquer SMTP.")

        self.host = ctk.CTkEntry(tab, placeholder_text="ex.: smtp.seudominio.com.br")
        self.host.insert(0, s.host)
        self._row(tab, 2, "Servidor SMTP", self.host)

        self.port = ctk.CTkEntry(tab, width=100)
        self.port.insert(0, str(s.port))
        self._row(tab, 3, "Porta", self.port)

        self.security = ctk.CTkOptionMenu(tab, values=list(SECURITY_LABELS.values()), command=self._on_security)
        self.security.set(SECURITY_LABELS.get(s.security, SECURITY_LABELS[SECURITY_STARTTLS]))
        self._row(tab, 4, "Segurança", self.security)

        self.auth_var = ctk.BooleanVar(value=s.auth)
        self.auth_check = ctk.CTkCheckBox(tab, text="O servidor exige usuário e senha", variable=self.auth_var,
                                          command=self._on_auth)
        self._row(tab, 5, "Login", self.auth_check)

        self.username = ctk.CTkEntry(tab)
        if s.username:
            self.username.insert(0, s.username)
        self._row(tab, 6, "Usuário de login", self.username)

        self.password = ctk.CTkEntry(tab, show="•")
        self.password_hint = self._row(tab, 7, "Senha", self.password, " ")

        self.from_address = ctk.CTkEntry(tab, placeholder_text="igual ao usuário de login")
        if s.from_address:
            self.from_address.insert(0, s.from_address)
        self._row(tab, 9, "Email do remetente", self.from_address,
                  "Endereço que aparece no “De”. Deixe em branco para usar o usuário de login "
                  "(quando ele for um email).")

        box = ctk.CTkFrame(tab, fg_color="transparent")
        box.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        box.grid_columnconfigure(1, weight=1)
        self.test_btn = ctk.CTkButton(box, text="Testar conexão", width=150, command=self.test_connection)
        self.test_btn.grid(row=0, column=0, sticky="w")
        self.test_status = ctk.CTkLabel(box, text="", anchor="w", justify="left", wraplength=440)
        self.test_status.grid(row=0, column=1, sticky="w", padx=12)

        self._apply_provider_texts()
        self._on_auth()

    def _on_provider(self, label: str) -> None:
        self.provider_key = next(k for k, p in SMTP_PROVIDERS.items() if p.label == label)
        provider = SMTP_PROVIDERS[self.provider_key]
        if self.provider_key != PROVIDER_CUSTOM:
            self.host.delete(0, "end")
            self.host.insert(0, provider.host)
            self.port.delete(0, "end")
            self.port.insert(0, str(provider.port))
            self.security.set(SECURITY_LABELS[provider.security])
            if not self.auth_var.get():
                self.auth_var.set(True)
                self._on_auth()
        elif self.host.get().strip().lower() in {p.host for p in SMTP_PROVIDERS.values() if p.host}:
            self.host.delete(0, "end")  # endereço de um provedor pronto não serve para “Outro servidor”
        self._apply_provider_texts()
        self._set_test_status("", ok=None)

    def _apply_provider_texts(self) -> None:
        provider = SMTP_PROVIDERS[self.provider_key]
        self.username.configure(placeholder_text=provider.username_hint)
        self.password_hint.title.configure(text=provider.password_label)  # type: ignore[attr-defined]
        if self.saved_password:
            self.password.configure(placeholder_text="•••••• salva no cofre do sistema")
        else:
            self.password.configure(placeholder_text=provider.password_label.lower())
        hint = provider.password_hint
        hint += (" " if hint else "") + "Fica guardada no cofre do sistema, não em arquivo."
        if self.saved_password:
            hint += " Deixe em branco para manter a já salva."
        self._set_hint(self.password_hint, hint)
        if hasattr(self, "daily_hint"):
            self._set_hint(self.daily_hint, self._daily_limit_text())

    def _on_auth(self) -> None:
        state = "normal" if self.auth_var.get() else "disabled"
        self.username.configure(state=state)
        self.password.configure(state=state)

    def _on_security(self, label: str) -> None:
        defaults = {
            SECURITY_LABELS[SECURITY_STARTTLS]: "587",
            SECURITY_LABELS[SECURITY_SSL]: "465",
            SECURITY_LABELS[SECURITY_NONE]: "25",
        }
        if label in defaults and self.port.get().strip() in ("587", "465", "25", ""):
            self.port.delete(0, "end")
            self.port.insert(0, defaults[label])

    def _typed_password(self) -> str:
        typed = self.password.get()
        # Senhas de app do Google são mostradas em blocos com espaços; nos outros provedores o espaço vale.
        return typed.replace(" ", "") if self.provider_key == "gmail" else typed

    def _security_value(self) -> str:
        label = self.security.get()
        return next(k for k, v in SECURITY_LABELS.items() if v == label)

    def test_connection(self) -> None:
        cfg, error = self._collect()
        if error:
            self._set_test_status(error, ok=False)
            return
        password = (self._typed_password() or get_password(cfg.smtp.username)) if cfg.smtp.auth else None
        self.test_btn.configure(state="disabled")
        self._set_test_status("Conectando…", ok=None)

        def done(result, exc):
            self.test_btn.configure(state="normal")
            ok, message = result if exc is None else (False, str(exc))
            self._set_test_status(("✔ " if ok else "✖ ") + message, ok=ok)

        run_in_background(self, lambda: test_connection(cfg, password), done)

    def _set_test_status(self, text: str, ok: bool | None) -> None:
        color = OK_COLOR if ok else ERROR_COLOR if ok is False else MUTED_TEXT
        self.test_status.configure(text=text, text_color=color)

    # --- Remetente ---
    def _build_sender(self, tab) -> None:
        tab.grid_columnconfigure(1, weight=1)
        self.display_name = ctk.CTkEntry(tab, placeholder_text="Ex.: Equipe de Eventos")
        if self.cfg.sender.display_name:
            self.display_name.insert(0, self.cfg.sender.display_name)
        self._row(tab, 0, "Nome do remetente", self.display_name,
                  "Aparece no lugar do endereço: “Equipe de Eventos <eventos@empresa.com>”.")
        self.reply_to = ctk.CTkEntry(tab, placeholder_text="opcional")
        if self.cfg.sender.reply_to:
            self.reply_to.insert(0, self.cfg.sender.reply_to)
        self._row(tab, 2, "Responder para", self.reply_to,
                  "Se preenchido, as respostas das pessoas vão para este endereço.")

    # --- Mensagem ---
    def _build_message(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)
        m = self.cfg.message
        self.bodies = {MODE_TEXT: m.text_body, MODE_HTML: m.html_body}
        self.mode = m.mode if m.mode in MODE_LABELS else MODE_TEXT
        self._preview_job: str | None = None
        self._insert_target = None

        # Barra superior: formato à esquerda, ações à direita.
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(6, 0))
        toolbar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(toolbar, text="Formato", anchor="w").grid(row=0, column=0, sticky="w", padx=(4, 12))
        self.mode_switch = ctk.CTkSegmentedButton(toolbar, values=list(MODE_LABELS.values()), command=self._on_mode)
        self.mode_switch.set(MODE_LABELS[self.mode])
        self.mode_switch.grid(row=0, column=1, sticky="w")
        self.preview_btn = ctk.CTkButton(toolbar, text="", width=150, command=self._toggle_preview)
        self.preview_btn.grid(row=0, column=3, sticky="e")
        ctk.CTkButton(
            toolbar, text="Restaurar padrão", width=140, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.restore_default,
        ).grid(row=0, column=4, sticky="e", padx=(8, 0))

        # Assunto
        subject_row = ctk.CTkFrame(tab, fg_color="transparent")
        subject_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        subject_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(subject_row, text="Assunto", anchor="w").grid(row=0, column=0, sticky="w", padx=(4, 12))
        self.subject = ctk.CTkEntry(subject_row)
        self.subject.insert(0, m.subject)
        self.subject.grid(row=0, column=1, sticky="ew")

        # Variáveis clicáveis
        chips = ctk.CTkFrame(tab, fg_color="transparent")
        chips.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(chips, text="Inserir variável:", text_color=MUTED_TEXT, font=font(12)).pack(
            side="left", padx=(4, 8))
        for var in ("{nome}", "{primeiro_nome}", "{email}", "{arquivo}"):
            ctk.CTkButton(
                chips, text=var, width=0, height=26, corner_radius=13, font=font(12),
                fg_color=("gray85", "gray25"), hover_color=("gray78", "gray32"), text_color=("gray10", "gray90"),
                command=lambda v=var: self._insert_variable(v),
            ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            chips, text="ou qualquer coluna da planilha: “Data do Curso” → {data_do_curso}",
            text_color=MUTED_TEXT, font=font(12),
        ).pack(side="left", padx=(6, 0))

        # Editor + prévia lado a lado
        self.message_area = ctk.CTkFrame(tab, fg_color="transparent")
        self.message_area.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        self.message_area.grid_rowconfigure(0, weight=1)

        editor = ctk.CTkFrame(self.message_area, fg_color=CARD_COLOR, corner_radius=10)
        editor.grid(row=0, column=0, sticky="nsew")
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(1, weight=1)
        self.editor_title = ctk.CTkLabel(editor, text="", font=font(13, "bold"), anchor="w")
        self.editor_title.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))
        self.body = ctk.CTkTextbox(editor, wrap="word", font=ctk.CTkFont(family="Menlo", size=12))
        self.body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.body.insert("1.0", self.bodies[self.mode])

        self.preview_panel = self._build_preview_panel(self.message_area)

        for widget in (self.body, self.subject):
            widget.bind("<FocusIn>", lambda _e, w=widget: setattr(self, "_insert_target", w), add="+")
            widget.bind("<KeyRelease>", lambda _e: self._schedule_preview(), add="+")
        for widget in (self.display_name, self.from_address, self.username):
            widget.bind("<KeyRelease>", lambda _e: self._schedule_preview(), add="+")

        self.preview_visible = True
        self._layout_message_area()
        self._update_editor_title()
        self._refresh_preview()

    def _build_preview_panel(self, parent) -> ctk.CTkFrame:
        """Cartão que imita o email como a pessoa vai recebê-lo."""
        panel = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=10)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Prévia do email", font=font(13, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        self.browser_btn = ctk.CTkButton(top, text="Abrir no navegador", width=140, height=26, font=font(12),
                                         command=self.open_in_browser)
        self.browser_btn.grid(row=0, column=1, sticky="e")

        sheet = ctk.CTkFrame(panel, fg_color=EMAIL_BG, corner_radius=8)
        sheet.grid(row=1, column=0, rowspan=3, sticky="nsew", padx=8, pady=(0, 8))
        sheet.grid_columnconfigure(0, weight=1)
        sheet.grid_rowconfigure(3, weight=1)

        self.preview_subject = ctk.CTkLabel(sheet, text="", font=font(16, "bold"), anchor="w", justify="left",
                                            text_color=EMAIL_TEXT, wraplength=420)
        self.preview_subject.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self.preview_headers = ctk.CTkLabel(sheet, text="", font=font(12), anchor="w", justify="left",
                                            text_color=EMAIL_MUTED, wraplength=420)
        self.preview_headers.grid(row=1, column=0, sticky="ew", padx=14)
        ctk.CTkFrame(sheet, height=1, fg_color=EMAIL_RULE).grid(row=2, column=0, sticky="new", padx=14, pady=(10, 0))
        self.preview_body = ctk.CTkTextbox(sheet, wrap="word", font=font(13), fg_color=EMAIL_BG,
                                           text_color=EMAIL_TEXT, border_width=0, activate_scrollbars=True)
        self.preview_body.grid(row=3, column=0, sticky="nsew", padx=6, pady=(4, 0))
        self.preview_attachment = ctk.CTkLabel(
            sheet, text="", font=font(12), anchor="w", corner_radius=6, fg_color=EMAIL_CHIP, text_color=EMAIL_TEXT)
        self.preview_attachment.grid(row=4, column=0, sticky="w", padx=14, pady=(6, 12), ipadx=8, ipady=2)

        self.preview_note = ctk.CTkLabel(panel, text="", font=font(11), text_color=MUTED_TEXT, anchor="w",
                                         justify="left", wraplength=440)
        self.preview_note.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))
        return panel

    def _layout_message_area(self) -> None:
        area = self.message_area
        if self.preview_visible:
            area.grid_columnconfigure(0, weight=1, uniform="msg")
            area.grid_columnconfigure(1, weight=1, uniform="msg")
            self.preview_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
            self.preview_btn.configure(text="Ocultar prévia")
            self._refresh_preview()
        else:
            self.preview_panel.grid_remove()
            area.grid_columnconfigure(0, weight=1, uniform="")
            area.grid_columnconfigure(1, weight=0, uniform="")
            self.preview_btn.configure(text="👁  Mostrar prévia")

    def _toggle_preview(self) -> None:
        self.preview_visible = not self.preview_visible
        self._layout_message_area()

    def _update_editor_title(self) -> None:
        self.editor_title.configure(
            text="Corpo do email (HTML)" if self.mode == MODE_HTML else "Corpo do email")
        self.browser_btn.grid() if self.mode == MODE_HTML else self.browser_btn.grid_remove()

    def _insert_variable(self, var: str) -> None:
        target = self._insert_target or self.body
        target.insert("insert", var)
        target.focus_set()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(200, self._refresh_preview)

    def _sample(self) -> tuple[str, str, str, str | None]:
        """(remetente, assunto, corpo em texto, corpo HTML ou None) com os dados de exemplo."""
        name = self.display_name.get().strip()
        address = self.from_address.get().strip() or self.username.get().strip() or "seu-email@exemplo.com"
        sender = f"{name} <{address}>" if name else address
        subject = render(self.subject.get(), SAMPLE_VARIABLES).replace("\n", " ").strip()
        body = self.body.get("1.0", "end-1c")
        if self.mode == MODE_HTML:
            html_body = render(body, SAMPLE_VARIABLES, escape_html=True)
            return sender, subject, html_to_text(html_body), html_body
        return sender, subject, render(body, SAMPLE_VARIABLES), None

    def _refresh_preview(self) -> None:
        self._preview_job = None
        if not self.preview_visible:
            return
        sender, subject, text_body, _html = self._sample()
        self.preview_subject.configure(text=subject or "(sem assunto)")
        lines = [f"De: {sender}", f"Para: {SAMPLE_NAME} <{SAMPLE_EMAIL}>"]
        if self.reply_to.get().strip():
            lines.append(f"Responder para: {self.reply_to.get().strip()}")
        self.preview_headers.configure(text="\n".join(lines))
        set_readonly_text(self.preview_body, text_body)
        self.preview_attachment.configure(text=f"📎  {SAMPLE_FILE}")

        notes = ["Exemplo com dados fictícios; no envio, cada pessoa recebe os próprios dados."]
        if self.mode == MODE_HTML:
            notes.append("Formato HTML: aqui aparece só o texto. Use “Abrir no navegador” para ver cores e estilos.")
        missing = unknown_variables(self.subject.get() + self.body.get("1.0", "end-1c"), SAMPLE_VARIABLES)
        if missing:
            notes.append(f"{', '.join(missing)} não existe no exemplo; no envio será trocado se houver uma coluna "
                         "com esse nome na planilha.")
        self.preview_note.configure(text=" ".join(notes))

    def _on_mode(self, label: str) -> None:
        self.bodies[self.mode] = self.body.get("1.0", "end-1c")
        self.mode = next(k for k, v in MODE_LABELS.items() if v == label)
        self.body.delete("1.0", "end")
        self.body.insert("1.0", self.bodies[self.mode])
        self._update_editor_title()
        self._refresh_preview()

    def restore_default(self) -> None:
        if not messagebox.askyesno("Restaurar modelo", "Substituir o texto atual pelo modelo padrão?", parent=self):
            return
        self.body.delete("1.0", "end")
        self.body.insert("1.0", DEFAULT_HTML_BODY if self.mode == MODE_HTML else DEFAULT_TEXT_BODY)
        self._refresh_preview()

    def open_in_browser(self) -> None:
        sender, subject, text_body, html_body = self._sample()
        safe = html.escape
        body = html_body if html_body is not None else f"<pre style='font:14px sans-serif;white-space:pre-wrap'>{safe(text_body)}</pre>"
        path = config_dir() / "previa_email.html"
        path.write_text(
            f"<!doctype html><meta charset='utf-8'><title>{safe(subject)}</title>"
            f"<div style='font:13px sans-serif;color:#555;line-height:1.6'>"
            f"<div style='font-size:18px;color:#111;font-weight:bold;margin-bottom:6px'>{safe(subject)}</div>"
            f"De: {safe(sender)}<br>Para: {safe(SAMPLE_NAME)} &lt;{safe(SAMPLE_EMAIL)}&gt;<br>"
            f"📎 {safe(SAMPLE_FILE)}</div><hr>{body}",
            encoding="utf-8",
        )
        webbrowser.open(path.as_uri())

    # --- Envio ---
    def _build_sending(self, tab) -> None:
        tab.grid_columnconfigure(1, weight=1)
        s = self.cfg.sending
        self.interval_mode = ctk.CTkSegmentedButton(
            tab, values=list(INTERVAL_MODES.values()), command=lambda _label: self._on_interval_mode())
        self.interval_mode.set(INTERVAL_MODES["random" if s.random_interval else "fixed"])
        self._row(tab, 0, "Tipo de intervalo", self.interval_mode)
        self.interval_mode.grid_configure(sticky="w")

        holder = ctk.CTkFrame(tab, fg_color="transparent")
        self.interval_hint = self._row(tab, 1, "Intervalo entre envios", holder, " ")
        holder.grid_configure(sticky="w")

        self.fixed_box = ctk.CTkFrame(holder, fg_color="transparent")
        self.interval = ctk.CTkEntry(self.fixed_box, width=100)
        self.interval.insert(0, f"{s.interval_seconds:g}")
        self.interval.pack(side="left")
        ctk.CTkLabel(self.fixed_box, text="segundos").pack(side="left", padx=8)

        self.random_box = ctk.CTkFrame(holder, fg_color="transparent")
        ctk.CTkLabel(self.random_box, text="Entre").pack(side="left", padx=(0, 8))
        self.random_min, self.random_min_unit = self._duration_input(self.random_box, s.random_min_seconds)
        ctk.CTkLabel(self.random_box, text="e").pack(side="left", padx=8)
        self.random_max, self.random_max_unit = self._duration_input(self.random_box, s.random_max_seconds)
        self._on_interval_mode()

        self.daily_limit = ctk.CTkEntry(tab, width=100)
        self.daily_limit.insert(0, str(s.daily_limit))
        self.daily_hint = self._row(tab, 3, "Limite diário", self.daily_limit, self._daily_limit_text())
        self.attempts = ctk.CTkEntry(tab, width=100)
        self.attempts.insert(0, str(s.max_attempts))
        self._row(tab, 5, "Tentativas por pessoa", self.attempts,
                  "Quantas vezes tentar de novo se a conexão falhar.")

    @staticmethod
    def _duration_input(parent, seconds: float) -> tuple[ctk.CTkEntry, ctk.CTkOptionMenu]:
        """Campo numérico + unidade (segundos/minutos); mostra em minutos quando o valor é minuto exato."""
        entry = ctk.CTkEntry(parent, width=80)
        unit = ctk.CTkOptionMenu(parent, values=list(TIME_UNITS), width=110)
        if seconds >= 60 and seconds % 60 == 0:
            entry.insert(0, f"{seconds / 60:g}")
            unit.set("minutos")
        else:
            entry.insert(0, f"{seconds:g}")
            unit.set("segundos")
        entry.pack(side="left")
        unit.pack(side="left", padx=(6, 0))
        return entry, unit

    @staticmethod
    def _read_duration(entry: ctk.CTkEntry, unit: ctk.CTkOptionMenu) -> float:
        return float(entry.get().replace(",", ".").strip()) * TIME_UNITS[unit.get()]

    def _is_random_interval(self) -> bool:
        return self.interval_mode.get() == INTERVAL_MODES["random"]

    def _on_interval_mode(self) -> None:
        if self._is_random_interval():
            self.fixed_box.pack_forget()
            self.random_box.pack(side="left")
            self._set_hint(self.interval_hint,
                           "A cada envio, o programa sorteia uma pausa entre o mínimo e o máximo. "
                           "Padrão: entre 30 segundos e 1 minuto. Pausas variadas parecem envios feitos à mão "
                           "e reduzem o risco de bloqueio, mas o envio total demora mais.")
        else:
            self.random_box.pack_forget()
            self.fixed_box.pack(side="left")
            self._set_hint(self.interval_hint,
                           "A mesma pausa entre todos os emails ajuda a evitar bloqueio por spam. "
                           "Recomendado: 5 segundos.")

    def _daily_limit_text(self) -> str:
        limit = SMTP_PROVIDERS[self.provider_key].daily_limit_hint
        limit = limit or "Confira o limite diário de envios do seu provedor."
        return (f"{limit} Use um valor um pouco abaixo do limite. Ao atingir o limite, o envio para e os "
                "restantes ficam pendentes para o dia seguinte.")

    # --- salvar ---
    def _collect(self) -> tuple[AppConfig, str | None]:
        cfg = copy.deepcopy(self.cfg)
        cfg.smtp.provider = self.provider_key
        cfg.smtp.host = self.host.get().strip()
        cfg.smtp.security = self._security_value()
        cfg.smtp.auth = bool(self.auth_var.get())
        cfg.smtp.username = self.username.get().strip()
        cfg.smtp.from_address = self.from_address.get().strip()
        cfg.sender.display_name = self.display_name.get().strip()
        cfg.sender.reply_to = self.reply_to.get().strip()
        self.bodies[self.mode] = self.body.get("1.0", "end-1c")
        cfg.message.mode = self.mode
        cfg.message.subject = self.subject.get().strip()
        cfg.message.text_body = self.bodies[MODE_TEXT]
        cfg.message.html_body = self.bodies[MODE_HTML]

        try:
            cfg.smtp.port = int(self.port.get().strip())
            assert 0 < cfg.smtp.port < 65536
        except (ValueError, AssertionError):
            return cfg, "Porta inválida (use um número de 1 a 65535; normalmente 587, 465 ou 25)."
        if not cfg.smtp.host:
            return cfg, "Informe o servidor SMTP."
        if cfg.smtp.from_address and not is_valid_email(cfg.smtp.from_address):
            return cfg, "O email do remetente não parece válido."
        if not cfg.smtp.from_address and cfg.smtp.username and not is_valid_email(cfg.smtp.username):
            return cfg, "O usuário de login não é um email: preencha o “Email do remetente”."
        if not cfg.smtp.auth and not cfg.smtp.from_address:
            return cfg, "Sem login, preencha o “Email do remetente”."
        if cfg.sender.reply_to and not is_valid_email(cfg.sender.reply_to):
            return cfg, "O email de “Responder para” não parece válido."
        cfg.sending.random_interval = self._is_random_interval()
        if cfg.sending.random_interval:
            try:
                low = self._read_duration(self.random_min, self.random_min_unit)
                high = self._read_duration(self.random_max, self.random_max_unit)
            except ValueError:
                return cfg, "Intervalo aleatório inválido: use números no mínimo e no máximo."
            if not 0 <= low <= high:
                return cfg, "Intervalo aleatório inválido: o mínimo precisa ser menor ou igual ao máximo."
            if high > MAX_INTERVAL_SECONDS:
                return cfg, "Intervalo aleatório inválido: o máximo pode ser de até 60 minutos."
            cfg.sending.random_min_seconds, cfg.sending.random_max_seconds = low, high
        else:
            try:
                cfg.sending.interval_seconds = float(self.interval.get().replace(",", ".").strip())
                assert 0 <= cfg.sending.interval_seconds <= 600
            except (ValueError, AssertionError):
                return cfg, "Intervalo inválido (use um número entre 0 e 600 segundos)."
        try:
            cfg.sending.daily_limit = int(self.daily_limit.get().replace(".", "").strip())
            assert cfg.sending.daily_limit > 0
        except (ValueError, AssertionError):
            return cfg, "Limite diário inválido (use um número maior que zero)."
        try:
            cfg.sending.max_attempts = int(self.attempts.get().strip())
            assert 1 <= cfg.sending.max_attempts <= 10
        except (ValueError, AssertionError):
            return cfg, "Tentativas inválidas (use um número de 1 a 10)."
        if not cfg.message.subject:
            return cfg, "Informe o assunto do email."
        return cfg, None

    # --- aba Sobre ---
    @staticmethod
    def _load_image(light: str, height: int, dark: str | None = None) -> ctk.CTkImage | None:
        """Imagem do app em `height` pontos de altura (nítida no Retina), ou None se não existir.

        Com `dark`, usa outra imagem no tema escuro (do mesmo tamanho da clara)."""
        try:
            from PIL import Image

            images = []
            for relative in (light, dark or light):
                image = Image.open(resource_path(relative))
                image.load()
                images.append(image)
        except Exception:  # noqa: BLE001 - imagem ausente ou inválida: a aba aparece sem ela
            return None
        width = round(images[0].width * height / images[0].height)
        return ctk.CTkImage(light_image=images[0], dark_image=images[1], size=(width, height))

    def _build_about(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        box = ctk.CTkFrame(tab, fg_color="transparent")
        box.grid(row=0, column=0)

        icon = self._load_image("assets/icon.png", 88)
        if icon is not None:
            ctk.CTkLabel(box, text="", image=icon).pack()
        ctk.CTkLabel(box, text=APP_TITLE, font=font(26, "bold")).pack(pady=(8, 0))
        ctk.CTkLabel(box, text=f"versão {__version__}", font=font(12), text_color=MUTED_TEXT).pack()
        ctk.CTkLabel(box, text=ABOUT_TEXT, font=font(13), wraplength=520, justify="center").pack(pady=(16, 0))

        ctk.CTkFrame(box, height=1, width=360, fg_color=("gray82", "gray28")).pack(pady=(22, 14))

        logo = self._load_image(AUTHOR_LOGO[0], 120, dark=AUTHOR_LOGO[1])
        if logo is not None:  # a logo já diz "desenvolvido por"
            ctk.CTkLabel(box, text="", image=logo).pack()
        else:
            ctk.CTkLabel(box, text="Desenvolvido por Catito", font=font(12), text_color=MUTED_TEXT).pack()
        ctk.CTkButton(
            box, text="GitHub · ocatito", width=200, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
            hover_color=("gray88", "gray25"), command=lambda: webbrowser.open(GITHUB_URL),
        ).pack(pady=(12, 0))

    def save(self) -> None:
        cfg, error = self._collect()
        if error:
            messagebox.showerror("Configurações", error, parent=self)
            return
        typed = self._typed_password()
        try:
            if not cfg.smtp.auth:
                pass
            elif typed and cfg.smtp.username:
                set_password(cfg.smtp.username, typed)
            elif cfg.smtp.username and cfg.smtp.username != self.cfg.smtp.username and self.saved_password:
                # Trocou o email de login sem digitar senha: leva a senha salva para o novo login.
                if not get_password(cfg.smtp.username):
                    set_password(cfg.smtp.username, self.saved_password)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Configurações", f"Não foi possível salvar a senha no cofre do sistema:\n{exc}",
                                 parent=self)
            return
        save_config(cfg)
        self.on_saved(cfg)
        self.on_exit()
