#!/usr/bin/env python3
"""Wrap a recorded .cast file into a standalone JS data-URL, so the slide
deck can embed it without a server (works when opened via file://).

Usage:
    python3 make-cast-js.py offline-assets/casts/toy.cast CAST_TOY

Writes offline-assets/casts/toy.js defining window.CAST_TOY_DATA_URL.
"""
import base64
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <path/to/recording.cast> <VAR_NAME>")

    cast_path = Path(sys.argv[1])
    var_name = sys.argv[2]

    raw = cast_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    data_url = f"data:text/plain;base64,{encoded}"

    out_path = cast_path.with_suffix(".js")
    out_path.write_text(f'window.{var_name}_DATA_URL = "{data_url}";\n')
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
