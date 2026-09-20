# AI API Proxy SDK for Python

<!-- conv-kit:v1 -->

<p align="center">
  <img src="assets/badges/price.svg" alt="observed unit price"> <img src="assets/badges/billing.svg" alt="billing model"> <img src="assets/badges/compat.svg" alt="OpenAI-compatible endpoint">
</p>

> **image2.5 from $0.0085 per 1K image** · Seedance 2.5 from $0.0961/sec · cached LLM input from $0.40/M — one OpenAI-compatible endpoint at `https://api.apimart.ai/v1`, no monthly plan required. *(observed 2026-09-17)*

**[Get an API key](https://go.apimart.ai/k-6a2a8a)** · **[Live pricing](https://go.apimart.ai/k-cb3758)**

**Why teams route through APIMart**

- **One key, entire catalog.** The same `https://api.apimart.ai/v1` base URL and `Authorization` header reach the whole catalog behind one key and 300+ other image, video and language models — switch the `model` field, not your client.
- **$1 minimum, pay as you go.** No subscription and no prepaid plan to size up front: top up from $1 and spend it on calls. There is no free quota to burn through first, so the price in this table is the price you pay.
- **The charge comes back in the response.** Every call reports the amount billed (`cost` / `credits_cost`), so a spend number is read per call instead of guessed at month end.
- **Async by design.** Submit, take the `task_id`, poll `GET /v1/tasks/{id}` — batching and retries are ordinary queue work, not a bespoke integration.

<!-- /conv-kit:v1 -->

A dependency-free Python client for **OpenAI-compatible AI API proxies**: idempotent submits, classed retries, task
polling with widening intervals, and cost accounting that sums what the gateway actually billed.

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


<!-- conv-kit:v1:scale -->
### What that costs at scale

| Workload | Cost at the observed rates |
| --- | --- |
| 1,000 GPT Image 2.5 renders (1K) | $8.50 |
| 10 minutes of Seedance 2.5 at 480P (600s) | $57.66 |
| 1M cached LLM input tokens | from $0.40 |

Linear at the observed per-unit rate, no volume discount assumed. Snapshot 2026-09-17; re-check the live table before committing a budget.
<!-- /conv-kit:v1:scale -->

<!-- conv-kit:v1:fix -->
## First-call troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `401` / `invalid api key` | key missing, truncated, or a stray newline pasted into the header | Re-copy it from the console; the header is `Authorization: Bearer $APIMART_API_KEY` |
| balance / credit error | the account has no balance | Top up from $1 in the console — there is no free quota to fall back on |
| `429` | concurrent requests on one key | Back off, then retry the same request with the same `Idempotency-Key` |
| `400` / model not found | wrong route for the id: the per-unit alias needs its `version`, the official id must not send one | Copy the exact `model` value from the route table above |
| task ends `failed` | prompt rejected by the filter, or a reference image URL expired | Re-submit with a **new** `Idempotency-Key` and re-host the reference image |
| result URL stops working | result links expire | Download the file as soon as the task reports `completed` |
<!-- /conv-kit:v1:fix -->

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

<!-- conv-kit:v1:cta -->
---

**Start with $1.** [Get an API key](https://go.apimart.ai/k-6a2a8a) → [check live pricing](https://go.apimart.ai/k-cb3758). The first call is three steps: submit, poll `task_id`, read the charged amount off the response.
<!-- /conv-kit:v1:cta -->

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
