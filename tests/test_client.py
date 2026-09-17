"""Offline tests: the transport is injected, so nothing here touches the network."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from apiproxy import Client, RetryableError, TerminalError  # noqa: E402


class FakeTransport:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(script):
    return Client(api_key="test-key", base_url="https://example.test/v1",
                  transport=FakeTransport(script), sleeper=lambda _s: None)


class RetryTests(unittest.TestCase):
    def test_retryable_then_success_reuses_idempotency_key(self):
        c = client([(429, {"error": "slow down"}), (200, {"data": {"id": "task_1"}})])
        task_id = c.submit_image("gpt-image-2.5-ext", "a cup", version="flare")
        self.assertEqual(task_id, "task_1")
        keys = {call["headers"].get("Idempotency-Key") for call in c.transport.calls}  # type: ignore[attr-defined]
        self.assertEqual(len(keys), 1, "a retry must reuse the original idempotency key")

    def test_terminal_error_does_not_retry(self):
        c = client([(400, {"error": "bad request"})])
        with self.assertRaises(TerminalError):
            c.submit_image("gpt-image-2.5-ext", "a cup")
        self.assertEqual(len(c.transport.calls), 1)  # type: ignore[attr-defined]

    def test_exhausted_retries_raise_retryable(self):
        c = client([(503, {})] * 4)
        with self.assertRaises(RetryableError):
            c.submit_image("gpt-image-2.5-ext", "a cup")


class AsyncRouteTests(unittest.TestCase):
    def test_generate_image_polls_and_records_cost(self):
        c = client([
            (200, {"data": {"id": "task_42"}}),
            (200, {"data": {"id": "task_42", "status": "processing"}}),
            (200, {"data": {"id": "task_42", "status": "completed", "cost": 0.0085, "credits_cost": 0.085,
                            "result": {"images": [{"url": ["https://example.test/out.png"]}]}}}),
        ])
        task = c.generate_image("gpt-image-2.5-ext", "a cup", version="flare")
        self.assertTrue(task.done)
        self.assertEqual(task.cost, 0.0085)
        self.assertEqual(task.urls, ["https://example.test/out.png"])
        report = c.cost_report()
        self.assertEqual(report["gpt-image-2.5-ext"]["tasks"], 1)
        self.assertAlmostEqual(report["gpt-image-2.5-ext"]["cost"], 0.0085)


class ChatTests(unittest.TestCase):
    def test_chat_posts_expected_body(self):
        c = client([(200, {"choices": [{"message": {"content": "hi"}}]})])
        c.chat("gpt-5.5", [{"role": "user", "content": "hi"}])
        call = c.transport.calls[0]  # type: ignore[attr-defined]
        self.assertTrue(call["url"].endswith("/chat/completions"))
        self.assertIn(b"gpt-5.5", call["body"])


if __name__ == "__main__":
    unittest.main()
