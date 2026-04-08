import sys
import os
from pathlib import Path

# Some locked-down environments block creating/writing `__pycache__`.
# Prevent tests from failing due to bytecode write attempts.
sys.dont_write_bytecode = True

# MoviePy can import Matplotlib, which tries to write a cache under the user profile.
# In locked-down environments this can raise noisy PermissionErrors at exit.
_mpl_dir = Path(__file__).resolve().parent / "_tmp_mplconfig"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))
os.environ.setdefault("MPLBACKEND", "Agg")
