from __future__ import annotations

from collections.abc import Sequence


MIN_SUPPORTED_PYTHON = (3, 11)
MAX_SUPPORTED_PYTHON_EXCLUSIVE = (3, 13)
PYTHON_REQUIREMENT_TEXT = "Recommended: Python 3.11 | Supported: Python 3.11-3.12 | Unsupported: Python 3.13+"
REQUIRED_NODE_MAJOR = 20
NODE_REQUIREMENT_TEXT = "Node.js 20.x is required."


def normalize_python_version(version_info: Sequence[int]) -> tuple[int, int, int]:
    major = int(version_info[0])
    minor = int(version_info[1]) if len(version_info) > 1 else 0
    micro = int(version_info[2]) if len(version_info) > 2 else 0
    return major, minor, micro


def is_supported_python_version(version_info: Sequence[int]) -> bool:
    major, minor, _micro = normalize_python_version(version_info)
    return MIN_SUPPORTED_PYTHON <= (major, minor) < MAX_SUPPORTED_PYTHON_EXCLUSIVE


def python_version_error_message(version_info: Sequence[int]) -> str:
    major, minor, micro = normalize_python_version(version_info)
    return (
        f"Python 3.11 or 3.12 is required. Current version: {major}.{minor}.{micro}\n"
        f"{PYTHON_REQUIREMENT_TEXT}"
    )


def parse_node_major(version_text: str) -> int | None:
    normalized = version_text.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    major_text = normalized.split(".", 1)[0]
    try:
        return int(major_text)
    except ValueError:
        return None


def is_supported_node_version(version_text: str) -> bool:
    return parse_node_major(version_text) == REQUIRED_NODE_MAJOR


def node_version_error_message(version_text: str) -> str:
    current = version_text.strip() or "unknown"
    return f"{NODE_REQUIREMENT_TEXT} Current version: {current}"
