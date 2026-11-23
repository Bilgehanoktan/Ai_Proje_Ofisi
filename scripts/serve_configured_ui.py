"""Compatibility launcher for the real pinned Kernel binding; no demo writer."""

import sys
from pathlib import Path


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [
        str(root / "product/backend"),
        str(root / "contracts/source/python"),
        str(root / "verifier/src"),
    ]
    from company_os.api.http.kernel_binding import main as kernel_main

    return kernel_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
