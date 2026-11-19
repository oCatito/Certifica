import datetime as dt

import pytest
from openpyxl import Workbook

from app.core.spreadsheet import SpreadsheetError, read_sheet, suggest_columns


def test_csv_semicolon_utf8(tmp_path):
    p = tmp_path / "lista.csv"
    p.write_text("Nome;E-mail;Arquivo;Curso\nMarina Silva;marina@x.com;marina.pdf;Python Básico\n\n", encoding="utf-8-sig")
    sheet = read_sheet(p)
    assert sheet.headers == ["Nome", "E-mail", "Arquivo", "Curso"]
    assert sheet.rows == [{"Nome": "Marina Silva", "E-mail": "marina@x.com", "Arquivo": "marina.pdf", "Curso": "Python Básico"}]
    assert sheet.line_numbers == [2]


def test_csv_comma_latin1(tmp_path):
    p = tmp_path / "lista.csv"
    p.write_bytes("nome,email,arquivo\nJosé Álvares,jose@x.com,jose.pdf\n".encode("cp1252"))
    sheet = read_sheet(p)
    assert sheet.rows[0]["nome"] == "José Álvares"


def test_xlsx_with_dates_numbers_and_blank_columns(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append([None])  # linha vazia antes do cabeçalho
    ws.append(["Nome", "Email", "Arquivo", "Data", "Horas", None])
    ws.append(["Ana", "ana@x.com", "ana.pdf", dt.datetime(2026, 11, 3), 8.0, None])
    ws.append([None, None, None, None, None, None])
    ws.append(["Bia", "bia@x.com", "bia.pdf", dt.datetime(2026, 11, 4), 12.5, None])
    p = tmp_path / "lista.xlsx"
    wb.save(p)

    sheet = read_sheet(p)
    assert sheet.headers == ["Nome", "Email", "Arquivo", "Data", "Horas"]
    assert sheet.rows[0]["Data"] == "03/11/2026"
    assert sheet.rows[0]["Horas"] == "8"
    assert sheet.rows[1]["Horas"] == "12.5"
    assert sheet.line_numbers == [3, 5]


def test_duplicate_headers_get_suffix(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("nome;nome;email\na;b;c@d.com\n", encoding="utf-8")
    assert read_sheet(p).headers == ["nome", "nome (2)", "email"]


@pytest.mark.parametrize("content", ["", "nome;email\n"])
def test_empty_sheet_errors(tmp_path, content):
    p = tmp_path / "l.csv"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(SpreadsheetError):
        read_sheet(p)


def test_unsupported_format(tmp_path):
    p = tmp_path / "l.pdf"
    p.write_bytes(b"x")
    with pytest.raises(SpreadsheetError):
        read_sheet(p)


def test_suggest_columns():
    assert suggest_columns(["Nome completo", "E-mail", "Nome do arquivo", "Curso"]) == {
        "email": "E-mail",
        "file": "Nome do arquivo",
        "name": "Nome completo",
    }
    assert suggest_columns(["a", "b"]) == {"email": None, "file": None, "name": None}
