from backend import settings


def test_get_non_negative_int_accepts_zero(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_IP", "0")
    assert settings._get_non_negative_int("RATE_LIMIT_PER_IP", 100) == 0


def test_get_non_negative_int_accepts_positive_values(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_IP", "2")
    assert settings._get_non_negative_int("RATE_LIMIT_PER_IP", 100) == 2


def test_get_non_negative_int_falls_back_for_invalid_or_negative_values(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_IP", "-1")
    assert settings._get_non_negative_int("RATE_LIMIT_PER_IP", 100) == 100

    monkeypatch.setenv("RATE_LIMIT_PER_IP", "not-an-int")
    assert settings._get_non_negative_int("RATE_LIMIT_PER_IP", 100) == 100
