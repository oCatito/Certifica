"""Pré-verificação: valida cada linha da planilha e localiza o PDF de cada pessoa."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from app.core.spreadsheet import Sheet
from app.core.text import clean_email, file_key, format_person_name, normalize

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")


class Status(Enum):
    OK = "✅ OK"
    FILE_NOT_FOUND = "❌ Arquivo não encontrado"
    INVALID_EMAIL = "❌ Email inválido"
    DUPLICATE_EMAIL = "⚠ Email duplicado"
    ALREADY_SENT = "⏭ Já enviado"

    @property
    def is_problem(self) -> bool:
        return self is not Status.OK


@dataclass
class ColumnMapping:
    name: str
    email: str
    file: str


@dataclass
class Recipient:
    line: int
    name: str
    email: str
    filename: str
    file_path: Path | None
    row: dict[str, str] = field(default_factory=dict)
    status: Status = Status.OK
    detail: str = ""

    @property
    def sent_key(self) -> str:
        return make_sent_key(self.email, self.filename)


def make_sent_key(email: str, filename: str) -> str:
    return f"{normalize(email)}|{normalize(filename)}"


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def invalid_email_detail(email: str) -> str:
    """Explica ao usuário por que o email foi recusado."""
    if not email:
        return "Email vazio"
    if " " in email:
        return f"'{email}' tem espaço no meio"
    odd = sorted({c for c in email if ord(c) > 127})
    if odd:
        return (f"'{email}' tem acento ou caractere especial ({' '.join(odd)}); "
                "endereços de email não aceitam esses caracteres")
    return f"'{email}' não é um email válido"


def build_file_index(folder: Path) -> dict[str, Path]:
    """Mapa nome-normalizado -> arquivo, para a busca ignorar maiúsculas, acentos, espaços e _."""
    index: dict[str, Path] = {}
    for p in sorted(Path(folder).iterdir()):
        if p.is_file() and not p.name.startswith("."):
            index.setdefault(file_key(p.name), p)
    return index


def resolve_file(filename: str, index: dict[str, Path]) -> Path | None:
    name = (filename or "").strip()
    if not name:
        return None
    name = Path(name).name  # aceita caminhos na planilha, usa só o nome
    if not Path(name).suffix:
        name += ".pdf"
    return index.get(file_key(name))


def check_recipients(
    sheet: Sheet,
    mapping: ColumnMapping,
    folder: Path,
    sent_keys: set[str] | None = None,
) -> list[Recipient]:
    sent_keys = sent_keys or set()
    index = build_file_index(folder)
    first_line_by_email: dict[str, int] = {}
    result: list[Recipient] = []

    for row, line in zip(sheet.rows, sheet.line_numbers):
        email = clean_email(row.get(mapping.email, ""))
        filename = row.get(mapping.file, "").strip()
        rec = Recipient(
            line=line,
            name=format_person_name(row.get(mapping.name, "")),
            email=email,
            filename=filename,
            file_path=resolve_file(filename, index),
            row=row,
        )

        email_key = normalize(email)
        if not is_valid_email(email):
            rec.status = Status.INVALID_EMAIL
            rec.detail = invalid_email_detail(email)
        elif rec.file_path is None:
            rec.status = Status.FILE_NOT_FOUND
            rec.detail = "Coluna de arquivo vazia" if not filename else f"'{filename}' não está na pasta"
        elif rec.sent_key in sent_keys:
            rec.status = Status.ALREADY_SENT
            rec.detail = "Enviado em um envio anterior desta planilha"
        elif email_key in first_line_by_email:
            rec.status = Status.DUPLICATE_EMAIL
            rec.detail = f"Mesmo email da linha {first_line_by_email[email_key]}"

        if is_valid_email(email):
            first_line_by_email.setdefault(email_key, line)
        result.append(rec)

    return result
