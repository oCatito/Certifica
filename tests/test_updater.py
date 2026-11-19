from app.core import updater


def test_parse_version():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("1.10") == (1, 10)
    assert updater.parse_version("1.2.0-beta") == (1, 2, 0)
    assert updater.parse_version("latest") == ()


def test_is_newer():
    assert updater.is_newer("1.0.3", "1.0.2")
    assert updater.is_newer("v1.1", "1.0.9")
    assert updater.is_newer("1.10.0", "1.9.0")  # compara números, não texto
    assert not updater.is_newer("1.0.2", "1.0.2")
    assert not updater.is_newer("1.0", "1.0.0")
    assert not updater.is_newer("1.0.1", "1.0.2")
    assert not updater.is_newer("", "1.0.0")


def test_parse_release():
    data = {
        "tag_name": "v1.2.0",
        "html_url": "https://github.com/oCatito/certifica/releases/tag/v1.2.0",
        "assets": [
            {"name": "Certifica.exe", "browser_download_url": "https://x/Certifica.exe"},
            {"name": "Certifica-macOS.zip", "browser_download_url": "https://x/Certifica-macOS.zip"},
        ],
    }
    release = updater.parse_release(data)
    assert release.version == "1.2.0"
    assert release.assets["Certifica.exe"] == "https://x/Certifica.exe"
    assert updater.parse_release({**data, "prerelease": True}) is None
    assert updater.parse_release({**data, "tag_name": "nightly"}) is None


def test_check_for_update(monkeypatch):
    release = updater.Release("99.0.0", "https://x")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda: release)
    assert updater.check_for_update() is release
    monkeypatch.setattr(updater, "fetch_latest_release", lambda: updater.Release(updater.__version__, "https://x"))
    assert updater.check_for_update() is None


def test_download_reports_progress(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * 600_000)
    dest = tmp_path / "dest.bin"
    progress = []
    updater.download(source.as_uri(), dest, progress.append)
    assert dest.read_bytes() == source.read_bytes()
    assert progress[-1] == 1.0 and progress == sorted(progress)
    assert not (tmp_path / "dest.bin.part").exists()


def test_source_checkout_cannot_self_update():
    assert updater.install_target() is None  # rodando pelo código-fonte: só abre a página do release
    assert not updater.can_self_update(updater.Release("9.9.9", "https://x", {"Certifica.exe": "u",
                                                                              "Certifica-macOS.zip": "u"}))


def test_install_windows_swaps_executable(tmp_path, monkeypatch):
    exe = tmp_path / "Certifica.exe"
    exe.write_bytes(b"old")
    monkeypatch.setattr(updater, "download", lambda url, dest, cb=None: dest.write_bytes(b"new"))
    hidden = []
    monkeypatch.setattr(updater, "_set_hidden", lambda path, on: hidden.append((path.name, on)))
    updater._install_windows(exe, "https://x/Certifica.exe", None)
    assert exe.read_bytes() == b"new"
    assert hidden == [("Certifica.exe.old", True)]  # o antigo fica oculto até ser apagado
    assert (tmp_path / "Certifica.exe.old").read_bytes() == b"old"
    assert not (tmp_path / "Certifica.exe.new").exists()
