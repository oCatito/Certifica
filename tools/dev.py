"""Modo desenvolvimento: abre o app e reabre sozinho a cada arquivo salvo.

Uso:  .venv/bin/python tools/dev.py
Pare com Ctrl+C. Não precisa gerar o executável para ver as mudanças.
Só roda um por vez: se já houver outro aberto (em outro terminal), este avisa e sai.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH = [ROOT / "main.py", ROOT / "app", ROOT / "assets"]
EXTENSIONS = {".py", ".png", ".ico", ".icns"}
INTERVAL = 0.5
LOCK_FILE = ROOT / ".dev.lock"


def acquire_single_instance_lock():
    """Garante um único tools/dev.py por vez e devolve o arquivo de bloqueio (mantenha-o aberto).

    Cada tools/dev.py reabre o app a cada arquivo salvo: com dois rodando (por exemplo em dois
    terminais), todo salvamento abria duas janelas do app. O bloqueio é do sistema operacional,
    então some sozinho quando o processo termina, mesmo se travar: não sobra nada que impeça de
    abrir de novo.
    """
    handle = open(LOCK_FILE, "a+")
    try:
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            handle.seek(0)
            other = handle.read().strip()
        except OSError:
            other = ""
        handle.close()
        sys.exit(
            "Já existe um tools/dev.py rodando" + (f" (PID {other})" if other else "") + ".\n"
            "Cada um reabre o app a cada arquivo salvo, então dois abririam duas janelas.\n"
            "Feche o outro (Ctrl+C no terminal dele) e tente de novo."
        )
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def snapshot() -> dict[Path, float]:
    files: dict[Path, float] = {}
    for target in WATCH:
        paths = [target] if target.is_file() else target.rglob("*")
        for p in paths:
            if p.suffix in EXTENSIONS and "__pycache__" not in p.parts:
                try:
                    files[p] = p.stat().st_mtime
                except OSError:
                    pass
    return files


def start() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=ROOT)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _exit_on_signal(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    # Fechar o terminal (ou um kill) também fecha o app, sem deixar janela órfã.
    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if sig is not None:
            signal.signal(sig, _exit_on_signal)
    lock = acquire_single_instance_lock()  # noqa: F841 - precisa ficar aberto até o fim
    print("Modo desenvolvimento: o app reabre a cada arquivo salvo. Ctrl+C para sair.")
    state = snapshot()
    proc = start()
    exited_reported = False
    try:
        while True:
            time.sleep(INTERVAL)
            current = snapshot()
            if current != state:
                changed = sorted(p.relative_to(ROOT) for p in current.keys() ^ state.keys()
                                 | {p for p in current if p in state and current[p] != state[p]})
                state = current
                print(f"↻ Mudou: {', '.join(map(str, changed))} — reabrindo o app…")
                stop(proc)
                proc = start()
                exited_reported = False
            elif proc.poll() is not None and not exited_reported:
                code = proc.returncode
                print("App fechado." if code == 0 else f"App terminou com erro (código {code}).",
                      "Salve um arquivo para reabrir ou Ctrl+C para sair.")
                exited_reported = True
    except KeyboardInterrupt:
        print()
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
