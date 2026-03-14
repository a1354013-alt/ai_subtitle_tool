from celery import Celery

celery_app = Celery(
    "video_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

from celery.schedules import crontab

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,
    beat_schedule={
        "cleanup-old-files-every-hour": {
            "task": "tasks.cleanup_old_files",
            "schedule": crontab(minute=0, hour="*"), # 每小時執行一次
        },
    },
)
