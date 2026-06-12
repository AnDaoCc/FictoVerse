"""Convert packaging/assets/launcher-icon.png to multi-size launcher-icon.ico."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SIZES = (16, 32, 48, 64, 128, 256)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    png_path = root / "packaging" / "assets" / "launcher-icon.png"
    ico_path = root / "packaging" / "assets" / "launcher-icon.ico"

    if not png_path.is_file():
        print(f"[icon] missing source PNG: {png_path}", file=sys.stderr)
        return 1

    with Image.open(png_path) as img:
        rgba = img.convert("RGBA")
        rgba.save(ico_path, format="ICO", sizes=[(s, s) for s in SIZES])

    print(f"[icon] wrote {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
