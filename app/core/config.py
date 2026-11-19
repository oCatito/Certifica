"""Configurações do programa: JSON na pasta do usuário + senha no cofre do sistema (keyring)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from app import APP_NAME, LEGACY_APP_NAME
from app.paths import atomic_write_text, config_dir

KEYRING_SERVICE = f"{APP_NAME}-smtp"
LEGACY_KEYRING_SERVICE = f"{LEGACY_APP_NAME}-smtp"

SECURITY_STARTTLS = "starttls"
SECURITY_SSL = "ssl"
SECURITY_NONE = "none"

MODE_TEXT = "text"
MODE_HTML = "html"

DEFAULT_TEXT_BODY = """Olá, {nome}!

Segue em anexo o seu certificado.

Atenciosamente,
Equipe
"""

DEFAULT_HTML_BODY = """<div style="font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #222; max-width: 560px;">
  <h2 style="color: #1f6aa5; margin-bottom: 8px;">Seu certificado chegou!</h2>
  <p>Olá, <strong>{nome}</strong>!</p>
  <p>Segue em anexo o seu certificado.</p>
  <p>Atenciosamente,<br>Equipe</p>
</div>
"""


PROVIDER_CUSTOM = "custom"


@dataclass(frozen=True)
class SmtpProvider:
    """Valores prontos de um provedor de email conhecido."""

    label: str
    host: str
    port: int
    security: str
    username_hint: str = "seu-email@exemplo.com"
    password_label: str = "Senha"
    password_hint: str = ""
    daily_limit_hint: str = ""


SMTP_PROVIDERS: dict[str, SmtpProvider] = {
    "gmail": SmtpProvider(
        "Gmail / Google Workspace", "smtp.gmail.com", 587, SECURITY_STARTTLS, "seu-email@gmail.com", "Senha de app",
        "Use uma SENHA DE APP do Google (Conta Google → Segurança → Verificação em duas etapas → Senhas de app), "
        "não a senha normal.",
        "Gmail comum: cerca de 500 por dia. Google Workspace: cerca de 2.000 por dia.",
    ),
    "outlook": SmtpProvider(
        "Outlook.com / Hotmail", "smtp-mail.outlook.com", 587, SECURITY_STARTTLS, "seu-email@outlook.com", "Senha",
        "Use a senha da conta ou uma senha de app (se a verificação em duas etapas estiver ativa). "
        "A Microsoft pode bloquear login por SMTP em contas pessoais.",
        "Outlook.com: cerca de 300 por dia.",
    ),
    "office365": SmtpProvider(
        "Microsoft 365 (empresa)", "smtp.office365.com", 587, SECURITY_STARTTLS, "seu-email@empresa.com", "Senha",
        "O administrador precisa liberar “SMTP autenticado” para esta caixa de email no Microsoft 365.",
        "Microsoft 365: até 10.000 destinatários por dia.",
    ),
    "yahoo": SmtpProvider(
        "Yahoo Mail", "smtp.mail.yahoo.com", 465, SECURITY_SSL, "seu-email@yahoo.com", "Senha de app",
        "Gere uma senha de app em Conta Yahoo → Segurança da conta → Gerar senha de app.",
    ),
    "icloud": SmtpProvider(
        "iCloud Mail", "smtp.mail.me.com", 587, SECURITY_STARTTLS, "seu-email@icloud.com", "Senha de app",
        "Gere uma senha específica de app em account.apple.com → Login e Segurança.",
    ),
    "zoho": SmtpProvider(
        "Zoho Mail", "smtp.zoho.com", 465, SECURITY_SSL, "seu-email@seudominio.com", "Senha",
        "Contas com domínio próprio podem usar smtppro.zoho.com. Com verificação em duas etapas, use uma senha de app.",
    ),
    "hostinger": SmtpProvider(
        "Hostinger", "smtp.hostinger.com", 465, SECURITY_SSL, "contato@seudominio.com", "Senha",
        "Use o email completo e a senha da caixa criada no painel da Hostinger.",
    ),
    "locaweb": SmtpProvider(
        "Locaweb", "email-ssl.com.br", 465, SECURITY_SSL, "contato@seudominio.com.br", "Senha",
        "Use o email completo e a senha da caixa criada no painel da Locaweb.",
    ),
    "sendgrid": SmtpProvider(
        "SendGrid", "smtp.sendgrid.net", 587, SECURITY_STARTTLS, "apikey", "Chave de API",
        "O usuário de login é a palavra “apikey” e a senha é a chave de API. "
        "Preencha também o “Email do remetente” com um endereço verificado no SendGrid.",
    ),
    "brevo": SmtpProvider(
        "Brevo (Sendinblue)", "smtp-relay.brevo.com", 587, SECURITY_STARTTLS, "login SMTP do painel", "Chave SMTP",
        "Login e chave estão em Brevo → SMTP & API. "
        "Preencha também o “Email do remetente” com um endereço verificado no Brevo.",
    ),
    "ses": SmtpProvider(
        "Amazon SES", "email-smtp.us-east-1.amazonaws.com", 587, SECURITY_STARTTLS, "usuário SMTP do SES",
        "Senha SMTP",
        "Troque “us-east-1” pela região da sua conta. Use as credenciais SMTP do SES (não as chaves IAM comuns) "
        "e preencha o “Email do remetente” com um endereço verificado.",
    ),
    "mailgun": SmtpProvider(
        "Mailgun", "smtp.mailgun.org", 587, SECURITY_STARTTLS, "postmaster@seudominio.com", "Senha SMTP",
        "Use o login e a senha SMTP do domínio no painel do Mailgun (contas na UE: smtp.eu.mailgun.org).",
    ),
    PROVIDER_CUSTOM: SmtpProvider(
        "Outro servidor (personalizado)", "", 587, SECURITY_STARTTLS, "usuário ou email de login", "Senha",
        "Informe o servidor, a porta e o tipo de segurança fornecidos pelo seu provedor ou pela equipe de TI.",
    ),
}


def detect_provider(host: str) -> str:
    """Descobre o provedor pelo endereço do servidor (para configs antigas, sem o campo)."""
    host = host.strip().lower()
    for key, provider in SMTP_PROVIDERS.items():
        if key != PROVIDER_CUSTOM and provider.host == host:
            return key
    return PROVIDER_CUSTOM


@dataclass
class SmtpConfig:
    provider: str = "gmail"
    host: str = "smtp.gmail.com"
    port: int = 587
    security: str = SECURITY_STARTTLS
    auth: bool = True
    username: str = ""
    from_address: str = ""

    @property
    def sender_address(self) -> str:
        """Endereço que aparece no “De”: o email do remetente ou, se vazio, o login."""
        return self.from_address.strip() or self.username.strip()


@dataclass
class SenderConfig:
    display_name: str = ""
    reply_to: str = ""


@dataclass
class MessageConfig:
    mode: str = MODE_TEXT
    subject: str = "Seu certificado"
    text_body: str = DEFAULT_TEXT_BODY
    html_body: str = DEFAULT_HTML_BODY


@dataclass
class SendingConfig:
    interval_seconds: float = 5.0
    random_interval: bool = True
    random_min_seconds: float = 30.0
    random_max_seconds: float = 60.0
    daily_limit: int = 450
    max_attempts: int = 2

    def next_interval(self, rng: random.Random | None = None) -> float:
        """Pausa até o próximo envio: fixa, ou sorteada entre o mínimo e o máximo."""
        if not self.random_interval:
            return self.interval_seconds
        low, high = sorted((self.random_min_seconds, self.random_max_seconds))
        return (rng or random).uniform(low, high)

    @property
    def average_interval(self) -> float:
        if not self.random_interval:
            return self.interval_seconds
        return (self.random_min_seconds + self.random_max_seconds) / 2


@dataclass
class AppConfig:
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    sender: SenderConfig = field(default_factory=SenderConfig)
    message: MessageConfig = field(default_factory=MessageConfig)
    sending: SendingConfig = field(default_factory=SendingConfig)

    def smtp_incomplete_reason(self, has_password: bool) -> str | None:
        """Retorna o motivo se a configuração de SMTP não permite enviar, ou None se está ok."""
        if not self.smtp.host.strip():
            return "o servidor SMTP não foi informado"
        if self.smtp.auth and not self.smtp.username.strip():
            return "o usuário de login não foi informado"
        if self.smtp.auth and not has_password:
            return "a senha não foi salva"
        if "@" not in self.smtp.sender_address:
            return "o email do remetente não foi informado"
        return None


def format_seconds(seconds: float) -> str:
    """Ex.: 45 → “45 s”; 135 → “2 min 15 s”; 300 → “5 min”."""
    total = max(0, round(seconds))
    minutes, secs = divmod(total, 60)
    if not minutes:
        return f"{secs} s"
    return f"{minutes} min {secs} s" if secs else f"{minutes} min"


def config_file() -> Path:
    return config_dir() / "config.json"


def _from_dict(cls, data: dict):
    """Cria o dataclass ignorando chaves desconhecidas e mantendo o padrão das que faltam."""
    known = {f.name: f for f in fields(cls)}
    kwargs = {}
    for name, value in (data or {}).items():
        if name not in known:
            continue
        default = getattr(cls(), name)
        try:
            kwargs[name] = type(default)(value)
        except (TypeError, ValueError):
            pass
    return cls(**kwargs)


def load_config(path: Path | None = None) -> AppConfig:
    path = path or config_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppConfig()
    smtp_data = data.get("smtp", {}) or {}
    smtp = _from_dict(SmtpConfig, smtp_data)
    if "provider" not in smtp_data:
        smtp.provider = detect_provider(smtp.host)
    if smtp.provider not in SMTP_PROVIDERS:
        smtp.provider = PROVIDER_CUSTOM
    return AppConfig(
        smtp=smtp,
        sender=_from_dict(SenderConfig, data.get("sender", {})),
        message=_from_dict(MessageConfig, data.get("message", {})),
        sending=_from_dict(SendingConfig, data.get("sending", {})),
    )


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    atomic_write_text(path or config_file(), json.dumps(asdict(cfg), ensure_ascii=False, indent=2))


# --- senha no cofre do sistema (Keychain / Gerenciador de Credenciais) ---

def get_password(username: str) -> str | None:
    if not username:
        return None
    try:
        password = keyring.get_password(KEYRING_SERVICE, username)
        if password is None:
            # Senha salva quando o app se chamava "Certificados": copia para o nome novo.
            password = keyring.get_password(LEGACY_KEYRING_SERVICE, username)
            if password is not None:
                keyring.set_password(KEYRING_SERVICE, username, password)
        return password
    except KeyringError:
        return None


def set_password(username: str, password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, username, password)


def delete_password(username: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except (PasswordDeleteError, KeyringError):
        pass
