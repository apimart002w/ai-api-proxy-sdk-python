"""Minimal, dependency-free client for OpenAI-compatible AI API proxies.

Design goals:
  * one idempotency key per logical operation, reused across every retry;
  * error classification that decides retry vs fail (429/5xx retryable, 400/401/402 terminal);
  * submit -> poll for asynchronous routes, with per-task cost accounting;
  * injectable transport so the client is testable without network access.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

DEFAULT_BASE_URL = os.environ.get("APIMART_BASE_URL", "https://api.apimart.ai/v1")
DEFAULT_RESPONSE_VERSION = "2026-07-27"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
TERMINAL_STATUS = {400, 401, 402, 403, 404, 422}
DEFAULT_BACKOFF = (2.0, 8.0, 30.0)
DEFAULT_POLL_PLAN = (1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 10.0, 10.0, 10.0, 10.0)


class ProxyError(Exception):
    """Base class for every error this client raises."""


class TerminalError(ProxyError):
    """The request will never succeed as written: fix it before retrying."""

    def __init__(self, status: int, payload: Any = None):
        super().__init__(f"terminal error {status}: {payload}")
        self.status = status
        self.payload = payload


class RetryableError(ProxyError):
    """Transient failure: retry with the same idempotency key."""

    def __init__(self, status: int | None, payload: Any = None):
        super().__init__(f"retryable error {status}: {payload}")
        self.status = status
        self.payload = payload


@dataclass
class Task:
    id: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None
    credits_cost: float | None = None

    @property
    def done(self) -> bool:
        return self.status in {"completed", "failed"}

    @property
    def urls(self) -> list[str]:
        images = ((self.payload.get("result") or {}).get("images") or [])
        return list(images[0].get("url", [])) if images else []


Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, Any]]


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> tuple[int, Any]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:                     # HTTP status, JSON body
        raw = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500]}


class Client:
    """OpenAI-compatible proxy client with retries, idempotency and cost accounting."""

    def __init__(self, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL, *,
                 transport: Transport | None = None, timeout: float = 60.0,
                 backoff: Iterable[float] = DEFAULT_BACKOFF, poll_plan: Iterable[float] = DEFAULT_POLL_PLAN,
                 sleeper: Callable[[float], None] = time.sleep, response_version: str = DEFAULT_RESPONSE_VERSION):
        self.api_key = api_key or os.environ.get("APIMART_API_KEY", "")
        if not self.api_key:
            raise ValueError("api_key is required (or set APIMART_API_KEY)")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.backoff = tuple(backoff)
        self.poll_plan = tuple(poll_plan)
        self.sleep = sleeper
        self.response_version = response_version
        self._costs: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- transport
    def _call(self, method: str, path: str, body: dict | None = None,
              idempotency_key: str | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-APIMart-Response-Version": self.response_version,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        data = json.dumps(body).encode() if body is not None else None
        url = f"{self.base_url}{path}"

        last_error: Exception | None = None
        for attempt in range(len(self.backoff) + 1):
            try:
                status, payload = self.transport(method, url, headers, data, self.timeout)
            except Exception as exc:                                  # network layer
                last_error = RetryableError(None, type(exc).__name__)
                if attempt == len(self.backoff):
                    raise last_error
            else:
                if 200 <= status < 300:
                    return payload
                if status in RETRYABLE_STATUS:
                    last_error = RetryableError(status, payload)
                    if attempt == len(self.backoff):
                        raise last_error
                elif status in TERMINAL_STATUS:
                    raise TerminalError(status, payload)
                else:
                    last_error = ProxyError(f"unexpected status {status}: {payload}")
                    if attempt == len(self.backoff):
                        raise last_error
            self.sleep(self.backoff[min(attempt, len(self.backoff) - 1)] + random.uniform(0, 0.25))
        raise last_error or ProxyError("unreachable")

    # ---------------------------------------------------------------- text routes
    def chat(self, model: str, messages: list[dict[str, str]], *, stream: bool = False, **params: Any) -> Any:
        """POST /chat/completions. Streaming responses are returned verbatim for the caller to iterate."""
        body = {"model": model, "messages": messages, "stream": stream, **params}
        return self._call("POST", "/chat/completions", body, idempotency_key=str(uuid.uuid4()))

    # ---------------------------------------------------------------- async routes
    def submit_image(self, model: str, prompt: str, *, version: str | None = None, resolution: str = "1K",
                     size: str = "1:1", n: int = 1, references: list[str] | None = None,
                     idempotency_key: str | None = None) -> str:
        body: dict[str, Any] = {"model": model, "prompt": prompt, "resolution": resolution, "size": size, "n": n}
        if version:
            body["version"] = version
        if references:
            body["image_urls"] = references
        payload = self._call("POST", "/images/generations", body,
                             idempotency_key=idempotency_key or str(uuid.uuid4()))
        data = payload.get("data")
        task_id = data.get("id") if isinstance(data, dict) else None
        if not task_id:
            raise ProxyError(f"submit did not return a task id: {payload}")
        return task_id

    def poll_task(self, task_id: str) -> Task:
        payload = self._call("GET", f"/tasks/{task_id}")
        data = payload.get("data", payload)
        task = Task(id=data.get("id", task_id), status=data.get("status", "unknown"), payload=data,
                    cost=data.get("cost"), credits_cost=data.get("credits_cost"))
        return task

    def generate_image(self, model: str, prompt: str, **kwargs: Any) -> Task:
        """Submit then poll until the task finishes; the completed task is recorded for cost reporting."""
        task_id = self.submit_image(model, prompt, **kwargs)
        for delay in self.poll_plan:
            task = self.poll_task(task_id)
            if task.done:
                self._costs.append({"task_id": task.id, "model": model, "status": task.status,
                                    "cost": task.cost, "credits_cost": task.credits_cost})
                return task
            self.sleep(delay)
        raise RetryableError(None, f"poll timeout after {sum(self.poll_plan):.0f}s for task {task_id}")

    # ---------------------------------------------------------------- accounting
    def cost_report(self) -> dict[str, Any]:
        """Totals per model — sum this instead of counting submissions."""
        totals: dict[str, dict[str, float]] = {}
        for row in self._costs:
            entry = totals.setdefault(row["model"], {"tasks": 0, "cost": 0.0, "credits_cost": 0.0, "failed": 0})
            entry["tasks"] += 1
            entry["cost"] += float(row.get("cost") or 0)
            entry["credits_cost"] += float(row.get("credits_cost") or 0)
            if row.get("status") != "completed":
                entry["failed"] += 1
        return totals
