import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Keep tests from leaving artifacts inside the repository.
# Note: Python may still write bytecode for this package before this module runs;
# we remove the local __pycache__ directory at process exit.

# MoviePy can import Matplotlib, which tries to write a cache under the user profile.
# In locked-down environments this can raise noisy PermissionErrors at exit.
_mpl_dir = Path(tempfile.mkdtemp(prefix="ai_subtitle_tool_mplconfig_"))
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))
os.environ.setdefault("MPLBACKEND", "Agg")


def _cleanup_test_artifacts() -> None:
    # Remove matplotlib config dir (system temp).
    shutil.rmtree(_mpl_dir, ignore_errors=True)

    # Remove local test package bytecode cache if created.
    pycache = Path(__file__).resolve().parent / "__pycache__"
    shutil.rmtree(pycache, ignore_errors=True)


atexit.register(_cleanup_test_artifacts)
