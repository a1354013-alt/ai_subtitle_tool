import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "video_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=False, # 既然指定了台北時區，關閉 UTC 以避免混淆
    beat_schedule={
        "cleanup-old-files-every-hour": {
            "task": "tasks.cleanup_old_files",
            "schedule": crontab(minute=0, hour="*"), # 每小時執行一次
        },
    },
)
