import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Cada teste usa uma pasta de config temporária."""
    monkeypatch.setenv("CERTIFICA_CONFIG_DIR", str(tmp_path / "config"))


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def cert_folder(tmp_path):
    folder = tmp_path / "certificados"
    folder.mkdir()
    for name in ("marina_silva_de_souza.pdf", "joao_souza.PDF", "José_Álvares.pdf"):
        (folder / name).write_bytes(PDF_BYTES)
    return folder
