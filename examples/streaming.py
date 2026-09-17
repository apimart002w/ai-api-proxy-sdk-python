#!/usr/bin/env python3
"""Streaming chat: the client returns the raw response, the caller iterates the SSE lines."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = os.environ.get("APIMART_BASE_URL", "https://api.apimart.ai/v1")


def main() -> None:
    request = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=json.dumps({"model": "gpt-5.5", "stream": True,
                         "messages": [{"role": "user", "content": "Count to five."}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ['APIMART_API_KEY']}",
                 "Content-Type": "application/json", "X-APIMart-Response-Version": "2026-07-27"})
    with urllib.request.urlopen(request, timeout=60) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            delta = json.loads(chunk)["choices"][0]["delta"].get("content")
            if delta:
                print(delta, end="", flush=True)
    print()


if __name__ == "__main__":
    main()
