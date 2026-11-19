"""Montagem das mensagens e conexão SMTP."""

from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from app.core.config import MODE_HTML, SECURITY_NONE, SECURITY_SSL, AppConfig
from app.core.matcher import Recipient
from app.core.templates import build_variables, html_to_text, render
from app.core.text import nfc

TIMEOUT_SECONDS = 30


def local_hostname() -> str:
    """Nome enviado no EHLO, sem consultar o DNS.

    O padrão do smtplib é socket.getfqdn(), que faz uma busca reversa no DNS e pode levar
    dezenas de segundos em alguns Macs e redes, atrasando cada conexão.
    """
    try:
        name = socket.gethostname().strip()
    except OSError:
        name = ""
    return name if name.isascii() and "." in name else "localhost"


class RateLimitError(Exception):
    """O servidor recusou por excesso de envios."""


def recipient_variables(rec: Recipient) -> dict[str, str]:
    return build_variables(rec.row, rec.name, rec.email, rec.filename)


def render_for(cfg: AppConfig, rec: Recipient) -> tuple[str, str, str | None]:
    """Retorna (assunto, corpo em texto, corpo em HTML ou None)."""
    variables = recipient_variables(rec)
    subject = render(cfg.message.subject, variables).replace("\n", " ").strip()
    if cfg.message.mode == MODE_HTML:
        html_body = render(cfg.message.html_body, variables, escape_html=True)
        return subject, html_to_text(html_body), html_body
    return subject, render(cfg.message.text_body, variables), None


def build_message(
    cfg: AppConfig,
    rec: Recipient,
    to_address: str | None = None,
    subject_prefix: str = "",
) -> EmailMessage:
    subject, text_body, html_body = render_for(cfg, rec)
    sender = cfg.smtp.sender_address

    msg = EmailMessage()
    msg["From"] = formataddr((cfg.sender.display_name.strip(), sender)) if cfg.sender.display_name.strip() else sender
    msg["To"] = to_address or (formataddr((rec.name, rec.email)) if rec.name else rec.email)
    msg["Subject"] = subject_prefix + subject
    if cfg.sender.reply_to.strip():
        msg["Reply-To"] = cfg.sender.reply_to.strip()
    msg["Date"] = formatdate(localtime=True)
    domain = sender.split("@")[-1] if "@" in sender else None
    msg["Message-ID"] = make_msgid(domain=domain)

    msg.set_content(text_body)
    if html_body is not None:
        msg.add_alternative(html_body, subtype="html")

    if rec.file_path is None:
        raise FileNotFoundError(f"Certificado não encontrado: {rec.filename}")
    path = Path(rec.file_path)
    msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=nfc(path.name))
    return msg


class SmtpClient:
    """Conexão SMTP reaproveitada entre os envios, com reconexão quando cair."""

    def __init__(self, cfg: AppConfig, password: str | None):
        self.cfg = cfg
        self.password = password or ""
        self._conn: smtplib.SMTP | None = None

    def connect(self) -> None:
        self.close()
        host, port, security = self.cfg.smtp.host.strip(), int(self.cfg.smtp.port), self.cfg.smtp.security
        context = ssl.create_default_context()
        ehlo_name = local_hostname()
        if security == SECURITY_SSL:
            conn: smtplib.SMTP = smtplib.SMTP_SSL(
                host, port, local_hostname=ehlo_name, timeout=TIMEOUT_SECONDS, context=context
            )
        else:
            conn = smtplib.SMTP(host, port, local_hostname=ehlo_name, timeout=TIMEOUT_SECONDS)
            conn.ehlo()
            if security != SECURITY_NONE:
                conn.starttls(context=context)
                conn.ehlo()
        if self.cfg.smtp.auth and self.password:
            conn.login(self.cfg.smtp.username.strip(), self.password)
        self._conn = conn

    def ensure_connected(self) -> None:
        if self._conn is None:
            self.connect()
            return
        try:
            if self._conn.noop()[0] != 250:
                self.connect()
        except (smtplib.SMTPException, OSError):
            self.connect()

    def send(self, msg: EmailMessage) -> None:
        self.ensure_connected()
        assert self._conn is not None
        try:
            self._conn.send_message(msg)
        except smtplib.SMTPResponseException as exc:
            if is_rate_limit(exc):
                raise RateLimitError(smtp_error_text(exc)) from exc
            raise

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.quit()
            except (smtplib.SMTPException, OSError):
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def smtp_error_text(exc: smtplib.SMTPResponseException) -> str:
    message = exc.smtp_error
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    return f"{exc.smtp_code} {' '.join(str(message).split())}"


def is_rate_limit(exc: smtplib.SMTPResponseException) -> bool:
    text = smtp_error_text(exc).lower()
    if exc.smtp_code == 421:
        return True
    return exc.smtp_code in (450, 451, 452, 454, 550) and any(
        k in text for k in ("5.4.5", "4.7.0", "rate", "limit", "quota", "too many")
    )


def friendly_error(exc: BaseException, host: str = "") -> str:
    """Mensagem de erro em português para mostrar ao usuário."""
    host = host.lower()
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        tip = ""
        if "gmail" in host or "googlemail" in host:
            tip = ("Use uma SENHA DE APP (não a senha normal); a conta precisa ter a verificação em 2 etapas "
                   "ativada. ")
        elif any(k in host for k in ("outlook", "office365", "yahoo", "mail.me.com")):
            tip = "Se a conta tem verificação em 2 etapas, use uma senha de app. "
        return f"O servidor recusou o login. Confira o usuário e a senha. {tip}Detalhe: {smtp_error_text(exc)}"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return ("O servidor não aceita login ou STARTTLS nesta porta. Confira o tipo de segurança "
                f"ou desmarque “Exige login”. Detalhe: {exc}")
    if isinstance(exc, RateLimitError):
        return f"O servidor limitou os envios desta conta por enquanto. Tente novamente mais tarde. Detalhe: {exc}"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        details = "; ".join(f"{addr}: {code} {msg!r}" for addr, (code, msg) in exc.recipients.items())
        return f"Destinatário recusado pelo servidor ({details})"
    if isinstance(exc, smtplib.SMTPResponseException):
        return f"O servidor respondeu com erro: {smtp_error_text(exc)}"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "A conexão com o servidor caiu."
    if isinstance(exc, (socket.gaierror,)):
        return "Servidor não encontrado. Confira o endereço do servidor SMTP e a sua internet."
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "O servidor demorou demais para responder (tempo esgotado)."
    if isinstance(exc, ConnectionRefusedError):
        return "Conexão recusada. Confira o servidor, a porta e o tipo de segurança."
    if isinstance(exc, ssl.SSLError):
        return f"Erro de segurança (TLS/SSL). Confira a porta e o tipo de segurança. Detalhe: {exc}"
    if isinstance(exc, FileNotFoundError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def test_connection(cfg: AppConfig, password: str | None) -> tuple[bool, str]:
    client = SmtpClient(cfg, password)
    try:
        client.connect()
        return True, "Conexão e login realizados com sucesso!"
    except Exception as exc:  # noqa: BLE001 - qualquer erro vira mensagem para o usuário
        return False, friendly_error(exc, cfg.smtp.host)
    finally:
        client.close()


def send_test(cfg: AppConfig, password: str | None, rec: Recipient) -> tuple[bool, str]:
    """Envia o email de uma pessoa da lista para o próprio remetente."""
    to = cfg.smtp.sender_address
    try:
        msg = build_message(cfg, rec, to_address=to, subject_prefix="[TESTE] ")
        with SmtpClient(cfg, password) as client:
            client.send(msg)
        return True, f"Email de teste enviado para {to}.\nConfira sua caixa de entrada."
    except Exception as exc:  # noqa: BLE001
        return False, friendly_error(exc, cfg.smtp.host)
