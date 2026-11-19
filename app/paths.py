"""Caminhos do app (config, recursos empacotados) e utilitários de sistema."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import platformdirs

from app import APP_NAME, LEGACY_APP_NAME


def config_dir() -> Path:
    """Pasta onde ficam config.json, estado dos envios e contador diário."""
    override = os.environ.get("CERTIFICA_CONFIG_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))
        legacy = Path(platformdirs.user_config_dir(LEGACY_APP_NAME, appauthor=False))
        if not path.exists() and legacy.is_dir():
            try:  # o app se chamava "Certificados": leva as configurações e o histórico de envios
                legacy.rename(path)
            except OSError:
                pass
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Caminho de um arquivo em assets/, funcionando também dentro do executável do PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def open_path(path: Path | str) -> None:
    """Abre um arquivo ou pasta com o programa padrão do sistema."""
    path = str(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def atomic_write_text(path: Path, text: str) -> None:
    """Grava o arquivo de forma atômica (não corrompe se o programa fechar no meio)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
