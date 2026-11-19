import pytest
from openpyxl import load_workbook

from app.core.list_template import TEMPLATE_COLUMNS, TEMPLATE_EXAMPLES, write_template
from app.core.spreadsheet import SpreadsheetError, read_sheet, suggest_columns


def test_lista_tab_has_only_locked_frozen_header(tmp_path):
    path = write_template(tmp_path / "sub" / "modelo.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames == ["Lista", "Instruções"]
    ws = wb["Lista"]
    assert [c.value for c in ws[1]] == TEMPLATE_COLUMNS
    assert ws.max_row == 1
    assert ws.freeze_panes == "A2"
    assert ws.protection.sheet
    assert all(c.protection.locked for c in ws[1])
    assert ws.column_dimensions["A"].protection.locked is False

    with pytest.raises(SpreadsheetError):  # vazia: o usuário ainda precisa preencher
        read_sheet(path)


def test_examples_are_in_instructions_tab(tmp_path):
    path = write_template(tmp_path / "modelo.xlsx")
    rows = [list(r) for r in load_workbook(path)["Instruções"].iter_rows(values_only=True)]
    header_at = rows.index(TEMPLATE_COLUMNS)
    assert rows[header_at + 1:header_at + 1 + len(TEMPLATE_EXAMPLES)] == TEMPLATE_EXAMPLES


def test_filled_template_is_readable(tmp_path):
    path = write_template(tmp_path / "modelo.xlsx")
    wb = load_workbook(path)
    wb["Lista"].append(TEMPLATE_EXAMPLES[0])
    wb.save(path)
    sheet = read_sheet(path)
    assert sheet.rows == [dict(zip(TEMPLATE_COLUMNS, TEMPLATE_EXAMPLES[0]))]
    assert suggest_columns(sheet.headers) == {"name": "nome", "email": "email", "file": "arquivo_certificado"}


def test_missing_columns_ignores_case_and_spaces():
    from app.core.list_template import missing_columns

    assert missing_columns(["Nome", "E-mail", "Arquivo Certificado"]) == ["email"]
    assert missing_columns(["NOME", "Email", "arquivo_certificado", "Curso"]) == []
