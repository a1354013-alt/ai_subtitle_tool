import os
from types import SimpleNamespace

try:
    from celery import Celery
    from celery.schedules import crontab
except ImportError:
    Celery = None

    def crontab(*_args, **_kwargs):
        return None

from . import settings


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class FallbackAsyncResult:
    def __init__(self, task_id=None, result=None, status="SUCCESS"):
        self.id = task_id
        self.task_id = task_id
        self.result = result
        self.status = status
        self.info = None


class FallbackTask:
    def __init__(self, func, *, bind: bool = False, name: str | None = None):
        self.func = func
        self.bind = bind
        self.name = name or f"{func.__module__}.{func.__name__}"
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
        self.request = SimpleNamespace(delivery_info={})
        self.state_updates: list[dict] = []

    def update_state(self, *args, **kwargs):
        self.state_updates.append({"args": args, "kwargs": kwargs})

    def run(self, *args, **kwargs):
        if self.bind:
            return self.func(self, *args, **kwargs)
        return self.func(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def apply_async(self, args=None, kwargs=None, task_id=None, queue=None, **_options):
        self.request.delivery_info = {"routing_key": queue or "default"}
        result = self.run(*(args or ()), **(kwargs or {}))
        return FallbackAsyncResult(task_id=task_id, result=result)

    def s(self, *args, **kwargs):
        return FallbackSignature(self, args, kwargs)

    def si(self, *args, **kwargs):
        return self.s(*args, **kwargs)

    def set(self, **_options):
        return self

    def replace(self, workflow):
        if callable(workflow):
            return workflow()
        return workflow


class FallbackSignature:
    def __init__(self, task: FallbackTask, args, kwargs):
        self.task = task
        self.args = tuple(args)
        self.kwargs = dict(kwargs)
        self.options = {}

    def set(self, **options):
        self.options.update(options)
        return self

    def apply_async(self, task_id=None, **options):
        merged = {**self.options, **options}
        return self.task.apply_async(args=self.args, kwargs=self.kwargs, task_id=task_id, **merged)

    def __call__(self):
        return self.task.run(*self.args, **self.kwargs)


class FallbackCelery:
    def __init__(self, *_args, **_kwargs):
        self.conf = SimpleNamespace()

    def task(self, *decorator_args, **decorator_kwargs):
        bind = bool(decorator_kwargs.get("bind", False))
        name = decorator_kwargs.get("name")

        def decorate(func):
            return FallbackTask(func, bind=bind, name=name)

        if decorator_args and callable(decorator_args[0]):
            return decorate(decorator_args[0])
        return decorate


celery_app = (
    Celery(
        "video_tasks",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["backend.tasks"],
    )
    if Celery is not None
    else FallbackCelery()
)

CELERY_CONFIG = dict(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 統一使用 UTC，顯示層再轉換為本地時區
    enable_utc=True,
    timezone="UTC",
    # 任務超時設定
    task_soft_time_limit=1800,  # 30 分鐘
    task_time_limit=2100,       # 35 分鐘
    # 佇列設定
    task_default_queue="default",
    task_queues={
        "default": {
            "exchange": "default",
            "routing_key": "default",
        },
        "high_priority": {
            "exchange": "high_priority",
            "routing_key": "high_priority",
        },
    },
    beat_schedule={
        "cleanup-old-files-every-hour": {
            "task": "backend.tasks.cleanup_old_files",
            "schedule": crontab(minute=0, hour="*"),
        },
    },
)
if hasattr(celery_app.conf, "update"):
    celery_app.conf.update(CELERY_CONFIG)
else:
    for key, value in CELERY_CONFIG.items():
        setattr(celery_app.conf, key, value)

task_always_eager = (
    _env_truthy("CELERY_TASK_ALWAYS_EAGER")
    or _env_truthy("TESTING")
    or bool(os.getenv("PYTEST_CURRENT_TEST"))
)

task_eager_propagates = (
    _env_truthy("CELERY_TASK_EAGER_PROPAGATES")
    or _env_truthy("TESTING")
    or bool(os.getenv("PYTEST_CURRENT_TEST"))
)

celery_app.conf.task_always_eager = task_always_eager
celery_app.conf.task_eager_propagates = task_eager_propagates
