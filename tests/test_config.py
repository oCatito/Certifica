import json

from app.core.config import (
    PROVIDER_CUSTOM,
    SECURITY_NONE,
    SMTP_PROVIDERS,
    AppConfig,
    config_file,
    detect_provider,
    load_config,
    save_config,
)


def test_detect_provider_by_host():
    assert detect_provider("smtp.gmail.com") == "gmail"
    assert detect_provider(" SMTP.Office365.com ") == "office365"
    assert detect_provider("mail.minhaempresa.com.br") == PROVIDER_CUSTOM


def test_every_preset_has_host_except_custom():
    for key, provider in SMTP_PROVIDERS.items():
        assert bool(provider.host) == (key != PROVIDER_CUSTOM)


def test_old_config_without_provider_is_detected():
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"smtp": {"host": "smtp.zoho.com", "port": 465, "security": "ssl",
                                         "username": "a@b.com"}}), encoding="utf-8")
    cfg = load_config()
    assert cfg.smtp.provider == "zoho"
    assert cfg.smtp.auth is True
    assert cfg.smtp.sender_address == "a@b.com"


def test_round_trip_custom_server():
    cfg = AppConfig()
    cfg.smtp.provider = PROVIDER_CUSTOM
    cfg.smtp.host = "relay.interno"
    cfg.smtp.port = 25
    cfg.smtp.security = SECURITY_NONE
    cfg.smtp.auth = False
    cfg.smtp.from_address = "eventos@empresa.com"
    save_config(cfg)
    loaded = load_config()
    assert loaded.smtp == cfg.smtp


def test_sender_address_prefers_from_address():
    cfg = AppConfig()
    cfg.smtp.username = "apikey"
    cfg.smtp.from_address = "eventos@empresa.com"
    assert cfg.smtp.sender_address == "eventos@empresa.com"


def test_incomplete_reason():
    cfg = AppConfig()
    cfg.smtp.username = "apikey"
    assert cfg.smtp_incomplete_reason(has_password=False) == "a senha não foi salva"
    assert cfg.smtp_incomplete_reason(has_password=True) == "o email do remetente não foi informado"
    cfg.smtp.from_address = "eventos@empresa.com"
    assert cfg.smtp_incomplete_reason(has_password=True) is None

    no_auth = AppConfig()
    no_auth.smtp.auth = False
    no_auth.smtp.from_address = "eventos@empresa.com"
    assert no_auth.smtp_incomplete_reason(has_password=False) is None


def test_next_interval_fixed_and_random():
    import random

    from app.core.config import SendingConfig, format_seconds

    fixed = SendingConfig(random_interval=False, interval_seconds=2)
    assert fixed.next_interval() == 2 and fixed.average_interval == 2

    rnd = SendingConfig(random_interval=True, random_min_seconds=30, random_max_seconds=300)
    rng = random.Random(1)
    values = [rnd.next_interval(rng) for _ in range(200)]
    assert all(30 <= v <= 300 for v in values)
    assert len({round(v) for v in values}) > 50  # varia de verdade
    assert rnd.average_interval == 165

    assert format_seconds(45) == "45 s"
    assert format_seconds(135) == "2 min 15 s"
    assert format_seconds(300) == "5 min"


def test_random_interval_round_trip():
    cfg = AppConfig()
    cfg.sending.random_interval = True
    cfg.sending.random_min_seconds = 30
    cfg.sending.random_max_seconds = 300
    save_config(cfg)
    assert load_config().sending == cfg.sending


def test_default_interval_is_random_between_30s_and_1min():
    from app.core.config import SendingConfig

    cfg = SendingConfig()
    assert cfg.random_interval is True
    assert (cfg.random_min_seconds, cfg.random_max_seconds) == (30, 60)
    assert all(30 <= cfg.next_interval() <= 60 for _ in range(50))
