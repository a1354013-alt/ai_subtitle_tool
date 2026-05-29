import importlib


def test_celery_app_respects_always_eager_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setenv("CELERY_TASK_EAGER_PROPAGATES", "1")

    import backend.celery_app as celery_app
    importlib.reload(celery_app)

    assert celery_app.celery_app.conf.task_always_eager is True
    assert celery_app.celery_app.conf.task_eager_propagates is True


def test_celery_app_preserves_testing_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.delenv("CELERY_TASK_EAGER_PROPAGATES", raising=False)

    import backend.celery_app as celery_app
    importlib.reload(celery_app)

    assert celery_app.celery_app.conf.task_always_eager is True
    assert celery_app.celery_app.conf.task_eager_propagates is True


def test_celery_app_defaults_to_false_if_no_eager_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.delenv("CELERY_TASK_EAGER_PROPAGATES", raising=False)

    import backend.celery_app as celery_app
    importlib.reload(celery_app)

    assert celery_app.celery_app.conf.task_always_eager is False
    assert celery_app.celery_app.conf.task_eager_propagates is False
