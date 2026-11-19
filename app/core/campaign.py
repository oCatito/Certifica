"""Estado dos envios (quem já recebeu), contador diário e relatório."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.matcher import Recipient
from app.core.text import normalize
from app.paths import atomic_write_text, config_dir


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def campaign_id(spreadsheet: Path) -> str:
    """Identifica a lista pelo caminho e pelo conteúdo da planilha."""
    spreadsheet = Path(spreadsheet).resolve()
    h = hashlib.sha256()
    h.update(str(spreadsheet).encode("utf-8"))
    h.update(spreadsheet.read_bytes())
    return h.hexdigest()[:24]


class Campaign:
    """Registra cada email enviado de uma planilha, para não reenviar ao retomar."""

    def __init__(self, spreadsheet: Path, base_dir: Path | None = None):
        self.spreadsheet = Path(spreadsheet)
        folder = (base_dir or config_dir()) / "envios"
        self.path = folder / f"{campaign_id(self.spreadsheet)}.json"
        self._lock = threading.Lock()
        self.sent: dict[str, dict] = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.sent = data.get("sent", {})
        except (OSError, ValueError):
            pass

    @property
    def sent_keys(self) -> set[str]:
        return set(self.sent)

    def mark_sent(self, rec: Recipient) -> str:
        when = now_iso()
        with self._lock:
            self.sent[rec.sent_key] = {"nome": rec.name, "email": rec.email, "arquivo": rec.filename, "quando": when}
            data = {"planilha": str(self.spreadsheet.resolve()), "sent": self.sent}
            atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=1))
        return when


class DailyCounter:
    """Quantos emails a conta enviou nas últimas 24 horas (limite diário do provedor)."""

    WINDOW = dt.timedelta(hours=24)

    def __init__(self, account: str, base_dir: Path | None = None):
        self.account = normalize(account)
        self.path = (base_dir or config_dir()) / "contador_diario.json"
        self._lock = threading.Lock()

    def _load(self) -> dict[str, list[str]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _recent(self, stamps: list[str]) -> list[str]:
        cutoff = dt.datetime.now().astimezone() - self.WINDOW
        recent = []
        for s in stamps:
            try:
                if dt.datetime.fromisoformat(s) > cutoff:
                    recent.append(s)
            except ValueError:
                continue
        return recent

    def count(self) -> int:
        with self._lock:
            return len(self._recent(self._load().get(self.account, [])))

    def remaining(self, limit: int) -> int:
        return max(0, limit - self.count())

    def record(self) -> None:
        with self._lock:
            data = self._load()
            stamps = self._recent(data.get(self.account, []))
            stamps.append(now_iso())
            data[self.account] = stamps
            atomic_write_text(self.path, json.dumps(data))


# --- resultado e relatório ---

RESULT_SENT = "Enviado"
RESULT_FAILED = "Falhou"
RESULT_PENDING = "Pendente"


@dataclass
class SendResult:
    recipient: Recipient
    status: str = RESULT_PENDING
    when: str = ""
    error: str = ""


def write_report(results: list[SendResult], spreadsheet: Path) -> Path:
    """Salva relatorio_envio_AAAA-MM-DD_HHMM.xlsx ao lado da planilha."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Envio"
    headers = ["Linha", "Nome", "Email", "Arquivo", "Status", "Data/Hora", "Erro"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F6AA5")
    colors = {RESULT_SENT: "D9F2D9", RESULT_FAILED: "F8D7DA", RESULT_PENDING: "FFF3CD"}
    for r in results:
        rec = r.recipient
        try:
            when = dt.datetime.fromisoformat(r.when).strftime("%d/%m/%Y %H:%M:%S") if r.when else ""
        except ValueError:
            when = r.when
        ws.append([rec.line, rec.name, rec.email, rec.filename, r.status, when, r.error])
        fill = PatternFill("solid", fgColor=colors.get(r.status, "FFFFFF"))
        ws.cell(row=ws.max_row, column=5).fill = fill
    for col, width in zip("ABCDEFG", (7, 32, 34, 34, 11, 22, 60)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"relatorio_envio_{stamp}.xlsx"
    target = Path(spreadsheet).resolve().parent / name
    try:
        wb.save(target)
    except OSError:
        target = config_dir() / "relatorios" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
    return target
