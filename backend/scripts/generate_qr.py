#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["segno>=1.6"]
# ///
"""Generate a QR code PNG for a URL.

Standalone script: its dependency is declared inline (PEP 723) so it stays out
of the backend's runtime dependencies. `uv` installs it on first run.

Usage:
    ./scripts/generate_qr.py URL [-o OUTPUT] [--scale N] [--border N]

Example:
    ./scripts/generate_qr.py https://103apartment.com -o qr.png --scale 20
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import segno


def _url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise argparse.ArgumentTypeError(f"not an http(s) URL: {value!r}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a QR code PNG for a URL.")
    parser.add_argument("url", type=_url, help="URL to encode, e.g. https://example.com")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("qr.png"), help="output PNG path (default: qr.png)"
    )
    parser.add_argument(
        "--scale", type=int, default=10, help="pixel size of one QR module (default: 10)"
    )
    parser.add_argument(
        "--border", type=int, default=4, help="quiet-zone width in modules (default: 4)"
    )
    args = parser.parse_args()

    if args.output.suffix.lower() != ".png":
        parser.error(f"output must be a .png file: {args.output}")

    # Error level "h" (30% recovery) keeps the code scannable when printed
    # small or partly damaged.
    qr = segno.make(args.url, error="h", micro=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    qr.save(args.output, kind="png", scale=args.scale, border=args.border)

    print(f"Saved QR code for {args.url} to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
