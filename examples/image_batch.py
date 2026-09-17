#!/usr/bin/env python3
"""Batch image generation with a hard cost ceiling, using only the completed tasks' `cost` values."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from apiproxy import Client  # noqa: E402

PROMPTS = [
    "A ceramic espresso cup on a stone pedestal, soft window light",
    "A rainy Tokyo alley at night, neon reflections, cinematic still",
    "Overhead flat lay of a ramen bowl on a dark slate table",
]
CEILING_USD = 0.05


def main() -> None:
    client = Client()
    for prompt in PROMPTS:
        task = client.generate_image("gpt-image-2.5-ext", prompt, version="flare", resolution="1K")
        print(f"{task.status:9} cost={task.cost} urls={task.urls}")
        spent = sum(v["cost"] for v in client.cost_report().values())
        if spent >= CEILING_USD:
            print(f"ceiling reached: ${spent:.4f}")
            break
    print(client.cost_report())


if __name__ == "__main__":
    main()
