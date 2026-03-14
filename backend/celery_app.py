import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "video_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    # B) 高風險修復：一致化時區設定
    enable_utc=False,
    # 任務超時設定
    task_soft_time_limit=1800,  # 30 分鐘
    task_time_limit=2100,       # 35 分鐘
    beat_schedule={
        "cleanup-old-files-every-hour": {
            "task": "backend.tasks.cleanup_old_files",
            "schedule": crontab(minute=0, hour="*"),
        },
    },
)
