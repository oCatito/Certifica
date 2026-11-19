"""Procura versões novas no GitHub e atualiza o app no lugar.

No início, o app consulta o último release do repositório. Se houver versão mais nova, a janela principal
mostra um aviso. Ao clicar em atualizar:

- **Windows** (`Certifica.exe`): baixa o novo .exe, renomeia o atual para `.old` (o Windows deixa renomear um
  executável em uso), põe o novo no lugar e o abre. O `.old` é apagado na próxima abertura.
- **macOS** (`Certifica.app`): baixa o .zip, extrai ao lado do app, troca os bundles e abre o novo assim que
  este processo terminar.

Se não der para atualizar sozinho (rodando pelo código-fonte, pasta sem permissão de escrita, app aberto
direto do .zip baixado etc.), o botão abre a página do release no navegador.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import APP_NAME, __version__

REPO = "oCatito/certifica"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_SECONDS = 10
WINDOWS_ASSET = "Certifica.exe"
MAC_ASSET = "Certifica-macOS.zip"


class UpdateError(Exception):
    """Falha ao baixar ou instalar a atualização."""


@dataclass
class Release:
    version: str
    page_url: str
    assets: dict[str, str] = field(default_factory=dict)  # nome do arquivo -> link de download

    @property
    def download_url(self) -> str | None:
        name = platform_asset()
        return self.assets.get(name) if name else None


# --- versões ---

def parse_version(text: str) -> tuple[int, ...]:
    """"v1.2.3" -> (1, 2, 3). Ignora sufixos ("1.2.0-beta" -> (1, 2, 0))."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, cur = parse_version(candidate), parse_version(current)
    if not new:
        return False
    size = max(len(new), len(cur))
    return new + (0,) * (size - len(new)) > cur + (0,) * (size - len(cur))


# --- rede ---

def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:  # no executável, o Python pode não achar os certificados do sistema: usa os do certifi
        import certifi

        context.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    return context


def _open(url: str, accept: str | None = None):
    headers = {"User-Agent": f"{APP_NAME}/{__version__}"}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_ssl_context())


def parse_release(data: dict) -> Release | None:
    tag = str(data.get("tag_name") or "")
    if not parse_version(tag) or data.get("draft") or data.get("prerelease"):
        return None
    assets = {
        str(a.get("name")): str(a.get("browser_download_url"))
        for a in data.get("assets") or []
        if a.get("name") and a.get("browser_download_url")
    }
    return Release(version=tag.lstrip("vV"), page_url=str(data.get("html_url") or RELEASES_PAGE), assets=assets)


def fetch_latest_release() -> Release | None:
    with _open(LATEST_API, accept="application/vnd.github+json") as response:
        return parse_release(json.load(response))


def check_for_update() -> Release | None:
    """O último release, se for mais novo que esta versão. None se já estiver atualizado."""
    release = fetch_latest_release()
    if release is not None and is_newer(release.version):
        return release
    return None


def download(url: str, dest: Path, on_progress: Callable[[float], None] | None = None) -> None:
    """Baixa `url` em `dest`. on_progress recebe a fração de 0 a 1 (só quando o tamanho é conhecido)."""
    partial = dest.with_name(dest.name + ".part")
    with _open(url) as response, open(partial, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(256 * 1024):
            out.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(min(1.0, done / total))
    if total and done != total:
        partial.unlink(missing_ok=True)
        raise UpdateError("O download veio incompleto. Tente de novo.")
    os.replace(partial, dest)


# --- instalação ---

def platform_asset() -> str | None:
    if sys.platform.startswith("win"):
        return WINDOWS_ASSET
    if sys.platform == "darwin":
        return MAC_ASSET
    return None


def _mac_bundle() -> Path | None:
    exe = Path(sys.executable).resolve()  # .../Certifica.app/Contents/MacOS/Certifica
    bundle = exe.parents[2] if len(exe.parents) > 2 else None
    if bundle is None or bundle.suffix != ".app":
        return None
    return bundle


def install_target() -> Path | None:
    """O que será substituído (o .exe ou o .app), ou None se este app não pode se atualizar sozinho."""
    if not getattr(sys, "frozen", False):
        return None  # rodando pelo código-fonte
    if sys.platform.startswith("win"):
        target = Path(sys.executable).resolve()
    elif sys.platform == "darwin":
        target = _mac_bundle()
        # Aberto direto do .zip baixado, o macOS roda o app de uma cópia temporária e só de leitura.
        if target is None or "AppTranslocation" in str(target):
            return None
    else:
        return None
    return target if os.access(target.parent, os.W_OK) else None


def can_self_update(release: Release) -> bool:
    return install_target() is not None and release.download_url is not None


def open_release_page(release: Release | None = None) -> None:
    webbrowser.open(release.page_url if release else RELEASES_PAGE)


def cleanup_old_versions() -> None:
    """Apaga o que sobrou de uma atualização anterior (o .exe antigo no Windows)."""
    target = install_target()
    if target is None:
        return
    leftovers = [target.with_name(target.name + ".old")]
    if sys.platform == "darwin":
        leftovers += [target.with_name(f".{target.name}.old"), target.with_name(f".{target.name}.new")]
    for path in leftovers:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
        except OSError:
            pass  # ainda em uso: tenta de novo na próxima abertura


def download_and_install(release: Release, on_progress: Callable[[float], None] | None = None) -> None:
    """Baixa e põe a nova versão no lugar. Depois disso, chame `restart()` e feche o app."""
    target = install_target()
    url = release.download_url
    if target is None or url is None:
        raise UpdateError("Este app não pode se atualizar sozinho.")
    if sys.platform.startswith("win"):
        _install_windows(target, url, on_progress)
    else:
        _install_mac(target, url, on_progress)


def _set_hidden(path: Path, hidden: bool) -> None:
    """Liga ou desliga o atributo "oculto" de um arquivo no Windows. Em outros sistemas, não faz nada."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        attrs = kernel32.GetFileAttributesW(str(path))
        if attrs == -1 or attrs == 0xFFFFFFFF:
            return
        hidden_flag = 0x2  # FILE_ATTRIBUTE_HIDDEN
        kernel32.SetFileAttributesW(str(path), (attrs | hidden_flag) if hidden else (attrs & ~hidden_flag))
    except Exception:  # noqa: BLE001 - só cosmético
        pass


def _install_windows(exe: Path, url: str, on_progress) -> None:
    new = exe.with_name(exe.name + ".new")
    old = exe.with_name(exe.name + ".old")
    download(url, new, on_progress)
    try:
        if old.exists():
            old.unlink()
        os.replace(exe, old)  # o Windows deixa renomear o executável em uso, mas não sobrescrever
        _set_hidden(old, True)  # não aparece como um segundo ícone na pasta até ser apagado
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)  # desfaz: o app continua na versão atual
            _set_hidden(exe, False)
            raise
    except OSError as exc:
        new.unlink(missing_ok=True)
        raise UpdateError(f"Não foi possível substituir o programa: {exc}") from exc


def _install_mac(bundle: Path, url: str, on_progress) -> None:
    staging = bundle.with_name(f".{bundle.name}.new")
    old = bundle.with_name(f".{bundle.name}.old")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / MAC_ASSET
        download(url, archive, on_progress)
        staging.mkdir()
        # ditto preserva links simbólicos, permissões e a assinatura do app (o zip foi criado com ele)
        result = subprocess.run(["ditto", "-x", "-k", str(archive), str(staging)], capture_output=True, text=True)
    apps = list(staging.glob("*.app"))
    if result.returncode != 0 or len(apps) != 1:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("O arquivo baixado não contém o aplicativo.")
    try:
        os.replace(bundle, old)  # o processo atual segue rodando a partir dos arquivos movidos
        try:
            os.replace(apps[0], bundle)
        except OSError:
            os.replace(old, bundle)
            raise
    except OSError as exc:
        raise UpdateError(f"Não foi possível substituir o aplicativo: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restart() -> None:
    """Abre a versão instalada. O chamador deve fechar o app logo em seguida."""
    target = install_target()
    if target is None:
        return
    if sys.platform.startswith("win"):
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")  # o novo .exe não reaproveita a pasta deste
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        subprocess.Popen([str(target)], env=env, creationflags=flags, close_fds=True)
    else:
        # Espera este processo terminar, apaga o app antigo e abre o novo.
        old = target.with_name(f".{target.name}.old")
        script = 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; rm -rf "$2"; open "$3"'
        subprocess.Popen(["/bin/sh", "-c", script, "sh", str(os.getpid()), str(old), str(target)],
                         start_new_session=True, close_fds=True)
