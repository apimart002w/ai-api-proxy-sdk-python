# AI API Proxy SDK for Python

A dependency-free Python client for **OpenAI-compatible AI API proxies**: idempotent submits, classed retries, task
polling with widening intervals, and cost accounting that sums what the gateway actually billed.

**Attributed entry points:** [Browse the model catalog](https://go.apimart.ai/k-831e06) · [Current pricing](https://go.apimart.ai/k-cb3758) · [Get an API key](https://go.apimart.ai/k-6a2a8a)

```bash
python -m pip install -e .          # or copy apiproxy/ into your project — it has no dependencies
export APIMART_API_KEY=sk-...
```

```python
from apiproxy import Client

client = Client()                                  # base_url defaults to https://api.apimart.ai/v1
answer = client.chat("gpt-5.5", [{"role": "user", "content": "Name three retry rules."}])

task = client.generate_image("gpt-image-2.5-ext", "A ceramic espresso cup on a stone pedestal",
                             version="flare", resolution="1K")
print(task.status, task.cost, task.urls)

for model, totals in client.cost_report().items():
    print(model, totals)
```

## Why a proxy SDK instead of the vendor SDK

The vendor SDK assumes one vendor. A proxy client has to handle what sits in between:

| Concern | What this client does |
| --- | --- |
| Retry safety | one `Idempotency-Key` per logical operation, reused across every attempt |
| Error classes | `429` / `5xx` / network → `RetryableError`; `400` / `401` / `402` → `TerminalError` (never retried) |
| Async routes | submit → poll with a widening plan, then return a `Task` with `cost` and result URLs |
| Billing reality | `cost_report()` aggregates per model from completed tasks, not from submission counts |
| Testability | inject a `transport` callable; the shipped test-suite runs fully offline |

## API surface

| Method | Route | Notes |
| --- | --- | --- |
| `chat(model, messages, *, stream=False, **params)` | `POST /chat/completions` | returns the parsed payload; iterate the response yourself when streaming |
| `submit_image(model, prompt, *, version, resolution, size, n, references, idempotency_key)` | `POST /images/generations` | returns the task id; `references` maps to `image_urls` |
| `poll_task(task_id)` | `GET /tasks/{id}` | returns a `Task` with `status`, `cost` and `urls` |
| `generate_image(...)` | submit + poll | records the finished task for cost reporting |
| `cost_report()` | — | `{model: {tasks, cost, credits_cost, failed}}` |

`Task.urls` returns the result links, which expire — download outputs before the window closes.

## Error taxonomy

```python
from apiproxy import RetryableError, TerminalError

try:
    client.generate_image("gpt-image-2.5-ext", prompt)
except TerminalError as exc:      # 400/401/402/403/404/422: fix the request or the balance
    log.error("terminal %s %s", exc.status, exc.payload)
except RetryableError as exc:     # exhausted retries on 429/5xx/network: requeue, keep the idempotency key
    queue.retry_later(exc)
```

Retry policy shipped by default: backoff `2s → 8s → 30s` (+0–0.25s jitter), then give up; poll plan
`1,2,3,5,8,10,10,10,10,10` seconds. Both are constructor arguments, so tests run in zero time with `sleeper=lambda _: None`.

## Batch example with a cost ceiling

```python
from apiproxy import Client

client = Client()
for prompt in open("prompts.txt"):
    task = client.generate_image("gpt-image-2.5-ext", prompt.strip(), version="flare", resolution="1K")
    spent = sum(v["cost"] for v in client.cost_report().values())
    if spent > 5.00:
        break
print(client.cost_report())
```

See `examples/` for runnable versions and `tests/` for the offline test-suite.

## FAQ

**Is this an official OpenAI SDK replacement?**
No. It is a thin client for a proxy that speaks the OpenAI request shape but returns an async task model for image and
video routes. Use the vendor SDK when you talk to one vendor directly; use this when a gateway sits in between.

**Why reuse one idempotency key instead of generating a new one per attempt?**
Because a new key per attempt turns a timeout into a second billable generation. One key per logical operation lets the
gateway collapse retries into the original task.

**How do I test code that uses this client?**
Inject a transport: `Client(transport=fake)` where `fake(method, url, headers, body, timeout)` returns
`(status, payload)`. The repository's tests are the reference implementation.

**Does `cost_report()` match my invoice?**
It sums the `cost` field of completed tasks, which is the same number reconciliation should use. It cannot see failed
submissions that were never billed, and it does not include your own storage or egress.

## Related searches

- `ai api proxy`
- `ai api proxy python`
- `openai compatible client python`
- `api retry idempotency`
- `task polling sdk`
- `llm api cost accounting`
- `ai api gateway`

## Attributed links (how this repository is measured)

| Purpose | Attributed link | Target |
| --- | --- | --- |
| Browse the model catalog | <https://go.apimart.ai/k-831e06> | `apimart.ai` |
| Current pricing page | <https://go.apimart.ai/k-cb3758> | `apimart.ai/pricing` |
| Get an API key | <https://go.apimart.ai/k-6a2a8a> | `apimart.ai/keys` |

Outbound APIMart links are minted through the promo link API; hand-made tracking parameters are rejected by
`tools/check_links.py` in CI.

## Disclosure

This client is published to document a proxy integration pattern; it does not claim official status for any vendor.
Product names, model names and documentation belong to their respective owners, and relayed routes are third-party relay
endpoints rather than first-party vendor endpoints.

## Repository map

```text
apiproxy/client.py   the client (retries, idempotency, polling, cost accounting, injectable transport)
tests/               offline unit tests (no network)
examples/            chat, streaming, batch with cost ceiling
tools/check_links.py attribution guard (CI)
```

## License

MIT — see [LICENSE](LICENSE).
