import importlib

from backend.celery_app import FallbackCelery


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


def test_fallback_task_wrapper_supports_bound_run_call_and_apply_async():
    app = FallbackCelery("tests")
    states = []

    @app.task(bind=True)
    def demo_task(self, value):
        self.update_state(state="PROGRESS", meta={"value": value})
        return value + 1

    demo_task.update_state = lambda *args, **kwargs: states.append((args, kwargs))

    assert demo_task.run(1) == 2
    async_result = demo_task.apply_async(args=[2], task_id="task-1", queue="high_priority")

    assert async_result.id == "task-1"
    assert async_result.result == 3
    assert async_result.status == "SUCCESS"
    assert states == [
        ((), {"state": "PROGRESS", "meta": {"value": 1}}),
        ((), {"state": "PROGRESS", "meta": {"value": 2}}),
    ]
