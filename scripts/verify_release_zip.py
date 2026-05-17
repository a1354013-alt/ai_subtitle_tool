from __future__ import annotations

import argparse
import sys
from pathlib import Path

from make_release_zip import _assert_release_zip_clean


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify an existing ai_subtitle_tool release zip.")
    parser.add_argument("zip_path", help="Path to the release zip to verify")
    args = parser.parse_args(argv)

    zip_path = Path(args.zip_path).resolve()
    _assert_release_zip_clean(zip_path)
    print(str(zip_path))
    print("release zip verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
