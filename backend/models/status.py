from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Unified task status enumeration for backend/frontend API contract.

    These values must match the frontend TaskStatus type in types/task.ts.
    CANCELED is a terminal state surfaced directly to the frontend.
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELED = "CANCELED"
