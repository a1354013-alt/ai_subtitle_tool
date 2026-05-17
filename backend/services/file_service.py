import logging
import os
import uuid


logger = logging.getLogger(__name__)


def write_text_atomic(target_path: str, content: str) -> None:
    tmp_path = f"{target_path}.tmp.{uuid.uuid4().hex}"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            logger.warning("Failed to remove temp file: %s", tmp_path, exc_info=True)

