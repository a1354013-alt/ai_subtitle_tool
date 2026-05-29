from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Unified task status enumeration for backend/frontend API contract.

    These values must match the frontend TaskStatus type in types/task.ts.
    CANCELED is treated as a terminal state and reported as FAILURE via API.
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELED = "CANCELED"

