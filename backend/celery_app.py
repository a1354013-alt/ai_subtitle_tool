import os
from celery import Celery
from celery.schedules import crontab

from . import settings

def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

celery_app = Celery(
    "video_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.tasks"]
)

celery_app.conf.update(
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
