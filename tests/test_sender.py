"""Envio de ponta a ponta contra um servidor SMTP local (aiosmtpd), sem mandar emails reais."""

import email
import queue
import socket
from email import policy

import pytest
from aiosmtpd.controller import Controller

from app.core.campaign import RESULT_FAILED, RESULT_PENDING, RESULT_SENT, Campaign, DailyCounter
from app.core.config import MODE_HTML, SECURITY_NONE, AppConfig
from app.core.mailer import send_test
from app.core.matcher import ColumnMapping, Status, check_recipients
from app.core.sender import FinishedEvent, SendJob
from app.core.spreadsheet import read_sheet


class Handler:
    def __init__(self):
        self.messages = []
        self.reject = set()

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address in self.reject:
            return "550 5.1.1 User unknown"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(email.message_from_bytes(envelope.content, policy=policy.default))
        return "250 OK"


@pytest.fixture
def smtp_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = Handler()
    # server_hostname fixo: sem ele o aiosmtpd chama socket.getfqdn(), que é muito lento nas
    # máquinas macOS do GitHub Actions e estoura o tempo de inicialização do servidor.
    controller = Controller(handler, hostname="127.0.0.1", port=port, server_hostname="localhost")
    controller.start()
    yield handler, port
    controller.stop()


@pytest.fixture
def setup(tmp_path, cert_folder, smtp_server):
    handler, port = smtp_server
    sheet_path = tmp_path / "lista.csv"
    sheet_path.write_text(
        "Nome;Email;Arquivo;Curso\n"
        "Marina Silva de Souza;marina@x.com;marina_silva_de_souza.pdf;Python\n"
        "João Souza;joao@x.com;joao_souza.pdf;Excel\n"
        "José Álvares;jose@x.com;jose_alvares.pdf;Word\n",
        encoding="utf-8",
    )
    cfg = AppConfig()
    cfg.smtp.host, cfg.smtp.port, cfg.smtp.security = "127.0.0.1", port, SECURITY_NONE
    cfg.smtp.username = "eventos@empresa.com"
    cfg.sender.display_name = "Equipe Eventos"
    cfg.sender.reply_to = "contato@empresa.com"
    cfg.message.subject = "Certificado - {curso}"
    cfg.sending.interval_seconds = 0
    mapping = ColumnMapping(name="Nome", email="Email", file="Arquivo")
    sheet = read_sheet(sheet_path)
    campaign = Campaign(sheet_path)
    recs = check_recipients(sheet, mapping, cert_folder, campaign.sent_keys)
    return handler, cfg, sheet, mapping, cert_folder, campaign, recs


def run_job(cfg, recs, campaign):
    events = queue.Queue()
    job = SendJob(cfg, None, recs, campaign, DailyCounter(cfg.smtp.username), events)
    job.start()
    job.join(timeout=30)
    finished = [e for e in list(events.queue) if isinstance(e, FinishedEvent)]
    assert finished, "o envio não terminou"
    return finished[0]


def test_send_all_text_mode(setup):
    handler, cfg, sheet, mapping, folder, campaign, recs = setup
    assert all(r.status is Status.OK for r in recs)

    done = run_job(cfg, recs, campaign)
    assert done.counts == {RESULT_SENT: 3, RESULT_FAILED: 0, RESULT_PENDING: 0}
    assert done.report_path and done.report_path.exists()

    msg = handler.messages[0]
    assert msg["Subject"] == "Certificado - Python"
    assert msg["From"] == "Equipe Eventos <eventos@empresa.com>"
    assert msg["Reply-To"] == "contato@empresa.com"
    assert "marina@x.com" in msg["To"]
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Olá, Marina Silva de Souza!" in body
    attachments = list(msg.iter_attachments())
    assert [a.get_filename() for a in attachments] == ["marina_silva_de_souza.pdf"]
    assert attachments[0].get_content().startswith(b"%PDF")

    # Retomada: abrir a mesma planilha de novo marca todos como já enviados.
    again = check_recipients(sheet, mapping, folder, Campaign(sheet.path).sent_keys)
    assert all(r.status is Status.ALREADY_SENT for r in again)


def test_html_mode_has_text_alternative(setup):
    handler, cfg, *_ , campaign, recs = setup
    cfg.message.mode = MODE_HTML
    cfg.message.html_body = "<p>Olá, <b>{nome}</b> - {curso}</p>"
    run_job(cfg, recs[:1], campaign)
    msg = handler.messages[0]
    assert "<b>Marina Silva de Souza</b>" in msg.get_body(preferencelist=("html",)).get_content()
    assert "Olá, Marina Silva de Souza - Python" in msg.get_body(preferencelist=("plain",)).get_content()


def test_recipient_refused_marks_failed_and_continues(setup):
    handler, cfg, *_, campaign, recs = setup
    handler.reject.add("joao@x.com")
    done = run_job(cfg, recs, campaign)
    assert [r.status for r in done.results] == [RESULT_SENT, RESULT_FAILED, RESULT_SENT]
    assert "recusado" in done.results[1].error.lower()
    assert len(handler.messages) == 2


def test_daily_limit_stops_and_leaves_pending(setup):
    handler, cfg, *_, campaign, recs = setup
    cfg.sending.daily_limit = 2
    done = run_job(cfg, recs, campaign)
    assert [r.status for r in done.results] == [RESULT_SENT, RESULT_SENT, RESULT_PENDING]
    assert "Limite diário" in done.stop_reason
    assert DailyCounter(cfg.smtp.username).count() == 2


def test_cancel_before_start(setup):
    handler, cfg, *_, campaign, recs = setup
    events = queue.Queue()
    job = SendJob(cfg, None, recs, campaign, DailyCounter(cfg.smtp.username), events)
    job.cancel()
    job.start()
    job.join(timeout=10)
    assert all(r.status == RESULT_PENDING for r in job.results)
    assert handler.messages == []


def test_send_test_goes_to_sender(setup):
    handler, cfg, *_, campaign, recs = setup
    ok, info = send_test(cfg, None, recs[0])
    assert ok, info
    assert handler.messages[0]["To"] == "eventos@empresa.com"
    assert handler.messages[0]["Subject"].startswith("[TESTE] ")


def test_from_address_used_when_login_is_not_email(setup):
    handler, cfg, *_, campaign, recs = setup
    cfg.smtp.auth = False
    cfg.smtp.username = "apikey"
    cfg.smtp.from_address = "certificados@empresa.com"
    ok, info = send_test(cfg, None, recs[0])
    assert ok, info
    msg = handler.messages[0]
    assert msg["To"] == "certificados@empresa.com"
    assert msg["From"] == "Equipe Eventos <certificados@empresa.com>"
    assert "@empresa.com>" in msg["Message-ID"]


def test_accented_names_headers_and_attachment(tmp_path, smtp_server):
    import unicodedata

    from app.core.mailer import build_message
    from app.core.matcher import Recipient

    handler, port = smtp_server
    pdf = tmp_path / unicodedata.normalize("NFD", "João Conceição.pdf")
    pdf.write_bytes(b"%PDF-1.4")
    cfg = AppConfig()
    cfg.smtp.host, cfg.smtp.port, cfg.smtp.security = "127.0.0.1", port, SECURITY_NONE
    cfg.smtp.username = "eventos@empresa.com"
    cfg.sender.display_name = "Coordenação Pedagógica"
    cfg.message.subject = "Certificado — {nome}"
    cfg.message.text_body = "Olá, {primeiro_nome}! Curso: {curso}"
    rec = Recipient(2, "João Conceição", "joao@x.com", "joão conceição", pdf, row={"Curso": "Gestão & Inovação"})
    msg = build_message(cfg, rec)
    att = next(msg.iter_attachments())
    assert att.get_filename() == "João Conceição.pdf"
    assert unicodedata.is_normalized("NFC", att.get_filename())

    from app.core.mailer import SmtpClient
    with SmtpClient(cfg, None) as client:
        client.send(msg)
    got = handler.messages[0]
    assert got["Subject"] == "Certificado — João Conceição"
    assert got["To"].addresses[0].display_name == "João Conceição"
    assert got["From"].addresses[0].display_name == "Coordenação Pedagógica"
    assert "Olá, João! Curso: Gestão & Inovação" in got.get_body(("plain",)).get_content()
