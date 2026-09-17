#!/usr/bin/env python3
"""Chat through the proxy client."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from apiproxy import Client  # noqa: E402


def main() -> None:
    client = Client()
    payload = client.chat("gpt-5.5", [{"role": "user", "content": "Name three retry rules, one per line."}])
    print(payload["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
