"""Leitura da lista de pessoas em .xlsx ou .csv."""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from pathlib import Path

from app.core.text import nfc, normalize


class SpreadsheetError(Exception):
    """Erro de leitura da planilha, com mensagem pronta para o usuário."""


@dataclass
class Sheet:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]] = field(default_factory=list)
    line_numbers: list[int] = field(default_factory=list)  # linha na planilha original (1 = cabeçalho)


def read_sheet(path: Path | str) -> Sheet:
    path = Path(path)
    if not path.is_file():
        raise SpreadsheetError(f"Arquivo não encontrado: {path}")
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        raw_rows = _read_xlsx(path)
    elif suffix in (".csv", ".txt"):
        raw_rows = _read_csv(path)
    else:
        raise SpreadsheetError("Formato não suportado. Use uma planilha .xlsx ou .csv.")
    return _build_sheet(path, raw_rows)


def _cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0, 0):
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_xlsx(path: Path) -> list[list[str]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # arquivo corrompido, protegido por senha etc.
        raise SpreadsheetError(f"Não foi possível abrir a planilha: {exc}") from exc
    try:
        ws = wb.worksheets[0]
        return [[_cell_to_str(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _read_csv(path: Path) -> list[list[str]]:
    text = _decode(path.read_bytes())
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample else ""
        delimiter = max(";,\t", key=first_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[cell.strip() for cell in row] for row in reader]


def _build_sheet(path: Path, raw_rows: list[list[str]]) -> Sheet:
    # O cabeçalho é a primeira linha não vazia.
    header_index = next((i for i, row in enumerate(raw_rows) if any(c for c in row)), None)
    if header_index is None:
        raise SpreadsheetError("A planilha está vazia.")

    data = [
        (line, row)
        for line, row in enumerate(raw_rows[header_index + 1:], start=header_index + 2)
        if any(c for c in row)
    ]
    header_row = raw_rows[header_index]
    width = max([len(header_row)] + [len(r) for _, r in data])

    # Colunas sem cabeçalho e sem dados (comum em planilhas exportadas) são ignoradas.
    columns: list[tuple[int, str]] = []
    seen: set[str] = set()
    for i in range(width):
        name = nfc(header_row[i]).strip() if i < len(header_row) else ""
        if not name:
            if not any(i < len(r) and r[i] for _, r in data):
                continue
            name = f"Coluna {i + 1}"
        base, n = name, 2
        while name in seen:
            name = f"{base} ({n})"
            n += 1
        seen.add(name)
        columns.append((i, name))

    sheet = Sheet(path=path, headers=[name for _, name in columns])
    for line, row in data:
        sheet.rows.append({name: nfc(row[i] if i < len(row) else "") for i, name in columns})
        sheet.line_numbers.append(line)

    if not sheet.rows:
        raise SpreadsheetError("A planilha não tem nenhuma linha de dados abaixo do cabeçalho.")
    return sheet


_SUGGESTIONS = {
    "name": ("nome", "name", "participante", "aluno", "aluna", "pessoa"),
    "email": ("email", "e-mail", "mail", "correio"),
    "file": ("arquivo", "certificado", "file", "pdf", "anexo"),
}


def suggest_columns(headers: list[str]) -> dict[str, str | None]:
    """Sugere quais colunas são nome, email e arquivo, pelo nome do cabeçalho."""
    result: dict[str, str | None] = {}
    used: set[str] = set()
    for role in ("email", "file", "name"):
        keywords = _SUGGESTIONS[role]
        match = None
        for h in headers:  # primeiro: nome exato
            if h not in used and normalize(h) in keywords:
                match = h
                break
        if match is None:  # depois: contém a palavra
            for h in headers:
                if h not in used and any(k in normalize(h) for k in keywords):
                    match = h
                    break
        if match:
            used.add(match)
        result[role] = match
    return result
