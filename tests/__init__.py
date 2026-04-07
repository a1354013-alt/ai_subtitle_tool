import sys

# Some locked-down environments block creating/writing `__pycache__`.
# Prevent tests from failing due to bytecode write attempts.
sys.dont_write_bytecode = True
