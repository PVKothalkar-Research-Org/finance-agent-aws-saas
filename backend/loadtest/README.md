# Load testing

`locustfile.py` models one *analysis job* per simulated user (seed portfolio in Aurora, enqueue on SQS,
poll until `completed`/`failed`). Locust's statistics therefore report **end-to-end job latency (p50/p95)** and
**error rate** (failed + timed-out jobs).

```bash
cd backend
uv run python loadtest/run_profile.py                    # 10, 50, 100 concurrent jobs against AWS
uv run python loadtest/run_profile.py --stages 10 --duration 900 --max-error-rate 5
LOAD_MODE=mock uv run python loadtest/run_profile.py --duration 15   # no AWS: validates the harness
uv run locust -f loadtest/locustfile.py                  # interactive web UI
```

Results land in `loadtest/results/` (CSV per stage + `summary.md`). Real runs create many Bedrock calls:
start with `--stages 10`, watch cost, and expect Bedrock rate-limit retries to dominate p95 at 50-100.
Replaces the old 3-user `test_scale.py`.
