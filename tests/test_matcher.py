from pathlib import Path

from app.core.matcher import ColumnMapping, Status, check_recipients, is_valid_email, make_sent_key
from app.core.spreadsheet import Sheet

MAPPING = ColumnMapping(name="Nome", email="Email", file="Arquivo")


def make_sheet(rows):
    return Sheet(
        path=Path("lista.csv"),
        headers=["Nome", "Email", "Arquivo"],
        rows=[dict(zip(["Nome", "Email", "Arquivo"], r)) for r in rows],
        line_numbers=list(range(2, 2 + len(rows))),
    )


def test_statuses(cert_folder):
    sheet = make_sheet([
        ("Marina Silva de Souza", "marina@x.com", "marina_silva_de_souza.pdf"),
        ("João Souza", "joao@x.com", "joao_souza"),             # sem extensão, arquivo .PDF
        ("José Álvares", "jose@x.com", "jose_alvares.pdf"),     # sem acento na planilha
        ("Sem Arquivo", "sem@x.com", "nao_existe.pdf"),
        ("Email Ruim", "email-ruim", "marina_silva_de_souza.pdf"),
        ("Duplicado", "MARINA@x.com", "joao_souza.pdf"),
        ("Vazio", "", ""),
    ])
    recs = check_recipients(sheet, MAPPING, cert_folder)
    assert [r.status for r in recs] == [
        Status.OK,
        Status.OK,
        Status.OK,
        Status.FILE_NOT_FOUND,
        Status.INVALID_EMAIL,
        Status.DUPLICATE_EMAIL,
        Status.INVALID_EMAIL,
    ]
    assert recs[1].file_path.name == "joao_souza.PDF"
    assert recs[2].file_path.name == "José_Álvares.pdf"
    assert "linha 2" in recs[5].detail


def test_already_sent(cert_folder):
    sheet = make_sheet([("Marina", "marina@x.com", "marina_silva_de_souza.pdf")])
    sent = {make_sent_key("Marina@X.com", "MARINA_silva_de_souza.pdf")}
    recs = check_recipients(sheet, MAPPING, cert_folder, sent)
    assert recs[0].status is Status.ALREADY_SENT


def test_email_validation():
    assert is_valid_email("a.b+c@sub.dominio.com.br")
    for bad in ("", "a@b", "a b@c.com", "@c.com", "a@.com", "a@c..com"):
        assert not is_valid_email(bad), bad


def test_file_match_ignores_spaces_underscores_and_hyphens(cert_folder):
    sheet = make_sheet([
        ("Marina", "marina@x.com", "Marina Silva de Souza"),
        ("João", "joao@x.com", "JOÃO  SOUZA.pdf"),
        ("José", "jose@x.com", "josé-álvares"),
    ])
    recs = check_recipients(sheet, MAPPING, cert_folder)
    assert [r.status for r in recs] == [Status.OK] * 3
    assert [r.file_path.name for r in recs] == ["marina_silva_de_souza.pdf", "joao_souza.PDF", "José_Álvares.pdf"]


def test_file_match_with_decomposed_filename(tmp_path):
    import unicodedata

    (tmp_path / unicodedata.normalize("NFD", "Conceição.pdf")).write_bytes(b"%PDF")
    sheet = make_sheet([("Ana", "ana@x.com", "conceição")])
    assert check_recipients(sheet, MAPPING, tmp_path)[0].status is Status.OK


def test_email_invisible_chars_are_removed_and_accents_explained(cert_folder):
    sheet = make_sheet([
        ("Ana", "​Ana@X.com ", "marina_silva_de_souza"),
        ("João", "joão@x.com", "joao_souza"),
    ])
    recs = check_recipients(sheet, MAPPING, cert_folder)
    assert recs[0].status is Status.OK and recs[0].email == "Ana@X.com"
    assert recs[1].status is Status.INVALID_EMAIL
    assert "acento" in recs[1].detail and "ã" in recs[1].detail


def test_names_in_all_caps_or_lowercase_are_formatted(cert_folder):
    sheet = make_sheet([
        ("JOÃO DA CONCEIÇÃO", "a@x.com", "joao_souza"),
        ("maria josé dos santos", "b@x.com", "joao_souza"),
        ("Ronald McDonald", "c@x.com", "joao_souza"),
    ])
    names = [r.name for r in check_recipients(sheet, MAPPING, cert_folder)]
    assert names == ["João da Conceição", "Maria José dos Santos", "Ronald McDonald"]
