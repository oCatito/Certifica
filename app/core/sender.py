"""Envio em segundo plano: uma thread envia e a interface lê os eventos por uma fila."""

from __future__ import annotations

import queue
import smtplib
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.core.campaign import (
    RESULT_FAILED,
    RESULT_PENDING,
    RESULT_SENT,
    Campaign,
    DailyCounter,
    SendResult,
    now_iso,
    write_report,
)
from app.core.config import AppConfig, format_seconds
from app.core.mailer import RateLimitError, SmtpClient, build_message, friendly_error
from app.core.matcher import Recipient

RETRY_DELAY_SECONDS = 5


# Eventos enviados para a interface pela fila
@dataclass
class LogEvent:
    text: str
    level: str = "info"  # info | ok | error | warn


@dataclass
class ProgressEvent:
    done: int
    total: int
    sent: int
    failed: int
    quota_used: int
    quota_limit: int


@dataclass
class WaitEvent:
    """Pausa entre um envio e o próximo: a interface mostra um timer com estes segundos."""

    seconds: float


@dataclass
class PausedEvent:
    paused: bool


@dataclass
class FinishedEvent:
    results: list[SendResult]
    report_path: Path | None
    stop_reason: str = ""  # vazio = terminou normalmente
    counts: dict[str, int] = field(default_factory=dict)


class SendJob(threading.Thread):
    def __init__(
        self,
        cfg: AppConfig,
        password: str | None,
        recipients: list[Recipient],
        campaign: Campaign,
        counter: DailyCounter,
        events: queue.Queue,
        client: SmtpClient | None = None,
    ):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.recipients = recipients
        self.campaign = campaign
        self.counter = counter
        self.events = events
        self.client = client or SmtpClient(cfg, password)
        self.results = [SendResult(r) for r in recipients]
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()

    # --- controles chamados pela interface ---
    def pause(self) -> None:
        self._resume.clear()
        self.events.put(PausedEvent(True))

    def resume(self) -> None:
        self._resume.set()
        self.events.put(PausedEvent(False))

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # --- execução ---
    def _log(self, text: str, level: str = "info") -> None:
        self.events.put(LogEvent(text, level))

    def _progress(self, done: int) -> None:
        sent = sum(r.status == RESULT_SENT for r in self.results)
        failed = sum(r.status == RESULT_FAILED for r in self.results)
        self.events.put(
            ProgressEvent(done, len(self.results), sent, failed, self.counter.count(), self.cfg.sending.daily_limit)
        )

    def _wait(self, seconds: float) -> None:
        """Espera respeitando cancelar."""
        self._cancel.wait(max(0.0, seconds))

    def run(self) -> None:
        stop_reason = ""
        limit = self.cfg.sending.daily_limit
        attempts = max(1, self.cfg.sending.max_attempts)
        total = len(self.results)
        self._progress(0)
        self._log(f"Iniciando envio de {total} email(s)...")

        try:
            for i, result in enumerate(self.results):
                rec = result.recipient
                self._resume.wait()
                if self.cancelled:
                    stop_reason = "Envio cancelado pelo usuário."
                    break
                if self.counter.remaining(limit) <= 0:
                    stop_reason = (
                        f"Limite diário de {limit} emails atingido. "
                        "Abra a mesma planilha amanhã para enviar os pendentes (quem já recebeu será pulado)."
                    )
                    break

                try:
                    msg = build_message(self.cfg, rec)
                except Exception as exc:  # noqa: BLE001
                    result.status, result.error, result.when = RESULT_FAILED, friendly_error(exc, self.cfg.smtp.host), now_iso()
                    self._log(f"✖ {rec.email}: {result.error}", "error")
                    self._progress(i + 1)
                    continue

                for attempt in range(1, attempts + 1):
                    try:
                        self.client.send(msg)
                    except smtplib.SMTPAuthenticationError as exc:
                        stop_reason = friendly_error(exc, self.cfg.smtp.host)
                        break
                    except RateLimitError as exc:
                        stop_reason = friendly_error(exc, self.cfg.smtp.host)
                        break
                    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
                        result.status, result.error = RESULT_FAILED, friendly_error(exc, self.cfg.smtp.host)
                        break
                    except smtplib.SMTPResponseException as exc:
                        result.status, result.error = RESULT_FAILED, friendly_error(exc, self.cfg.smtp.host)
                        if exc.smtp_code >= 500:  # erro permanente, não adianta repetir
                            break
                    except (smtplib.SMTPException, OSError) as exc:
                        result.status, result.error = RESULT_FAILED, friendly_error(exc, self.cfg.smtp.host)
                        self.client.close()
                    else:
                        result.status, result.error = RESULT_SENT, ""
                        break

                    if attempt < attempts and not self.cancelled:
                        self._log(f"… {rec.email}: {result.error} Tentando de novo ({attempt + 1}/{attempts})", "warn")
                        self._wait(RETRY_DELAY_SECONDS)

                if stop_reason:
                    result.status, result.error = RESULT_PENDING, ""
                    break

                result.when = now_iso()
                if result.status == RESULT_SENT:
                    self.campaign.mark_sent(rec)
                    self.counter.record()
                    self._log(f"✔ {rec.name or rec.email} <{rec.email}>", "ok")
                else:
                    self._log(f"✖ {rec.email}: {result.error}", "error")
                self._progress(i + 1)

                if i < total - 1:
                    pause = self.cfg.sending.next_interval()
                    if self.cfg.sending.random_interval:
                        self._log(f"⏱ Próximo envio em {format_seconds(pause)} (intervalo aleatório).")
                    self.events.put(WaitEvent(pause))
                    self._wait(pause)
        finally:
            self.client.close()

        if stop_reason:
            self._log(stop_reason, "warn")
        report = None
        try:
            report = write_report(self.results, self.campaign.spreadsheet)
            self._log(f"Relatório salvo em: {report}")
        except Exception as exc:  # noqa: BLE001
            self._log(f"Não foi possível salvar o relatório: {exc}", "error")

        counts = {
            RESULT_SENT: sum(r.status == RESULT_SENT for r in self.results),
            RESULT_FAILED: sum(r.status == RESULT_FAILED for r in self.results),
            RESULT_PENDING: sum(r.status == RESULT_PENDING for r in self.results),
        }
        self.events.put(FinishedEvent(self.results, report, stop_reason, counts))
