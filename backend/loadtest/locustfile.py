"""Locust load profile for the analysis pipeline (SQS -> planner -> specialist agents -> Aurora).

Each simulated user submits one portfolio-analysis job at a time and waits for it to finish; one
"request" in Locust's statistics = one end-to-end job, so p50/p95 are job latencies and the
failure rate is the share of jobs that failed or timed out.

Modes (LOAD_MODE):
  real  (default) seed a user in Aurora, enqueue a job on SQS, poll the jobs table.  Needs AWS creds.
  mock  simulate latency and random failures locally - used by CI and to validate this file.

Run the 10 / 50 / 100 concurrent-job profile:   uv run python loadtest/run_profile.py
Single ad-hoc run (web UI):                     uv run locust -f loadtest/locustfile.py
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid

from locust import User, between, events, task

MODE = os.environ.get("LOAD_MODE", "real")
JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "300"))
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "5"))
QUEUE_NAME = os.environ.get("QUEUE_NAME", "finance-agent-aws-saas-analysis-jobs")
SYMBOLS = ["SPY", "BND", "VTI", "VXUS", "QQQ", "IWM", "EFA", "AGG", "VNQ", "GLD"]


class JobFailed(Exception):
    pass


class JobTimeout(Exception):
    pass


class PipelineClient:
    """Thin wrapper over the real system (lazy imports so mock mode needs no AWS packages)."""

    def __init__(self) -> None:
        import boto3
        from src import Database

        self.db = Database()
        self.sqs = boto3.client("sqs", region_name=os.environ.get("DEFAULT_AWS_REGION", "us-east-1"))
        self.queue_url = self.sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]

    def seed_job(self, accounts: int = 2, positions: int = 5) -> str:
        user_id = f"load_{uuid.uuid4().hex[:10]}"
        self.db.users.create_user(user_id, display_name="Load test", years_until_retirement=25,
                                  target_retirement_income=75000)
        account_ids = [self.db.accounts.create_account(user_id, f"Account {i + 1}", "load test", cash_balance=1000)
                       for i in range(accounts)]
        for i in range(positions):
            self.db.positions.add_position(account_ids[i % accounts], SYMBOLS[i % len(SYMBOLS)], 10 * (i + 1))
        job_id = self.db.jobs.create_job(user_id, "portfolio_analysis", {"load_test": True})
        assert job_id, "job insert returned no id"
        return job_id

    def enqueue(self, job_id: str) -> None:
        self.sqs.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps({"job_id": job_id}))

    def wait(self, job_id: str) -> None:
        deadline = time.time() + JOB_TIMEOUT_SECONDS
        while time.time() < deadline:
            job = self.db.jobs.find_by_id(job_id)
            if job and job["status"] == "completed":
                return
            if job and job["status"] == "failed":
                raise JobFailed(job.get("error_message") or "job failed")
            time.sleep(POLL_SECONDS)
        raise JobTimeout(f"job {job_id} not finished after {JOB_TIMEOUT_SECONDS}s")


class MockPipeline:
    """Latency + failure model used for local validation and CI."""

    def __init__(self) -> None:
        self.latency = (float(os.environ.get("MOCK_MIN_SECONDS", "0.05")), float(os.environ.get("MOCK_MAX_SECONDS", "0.4")))
        self.failure_rate = float(os.environ.get("MOCK_FAILURE_RATE", "0.05"))

    def run_job(self) -> None:
        time.sleep(random.uniform(*self.latency))
        if random.random() < self.failure_rate:
            raise JobFailed("simulated agent failure")


_shared: PipelineClient | MockPipeline | None = None


def pipeline() -> PipelineClient | MockPipeline:
    global _shared
    if _shared is None:
        _shared = MockPipeline() if MODE == "mock" else PipelineClient()
    return _shared


class AnalysisJobUser(User):
    """One concurrent analysis job at a time per simulated user."""

    wait_time = between(0.5, 2)

    @task
    def run_analysis_job(self) -> None:
        start = time.perf_counter()
        exception: Exception | None = None
        try:
            p = pipeline()
            if isinstance(p, MockPipeline):
                p.run_job()
            else:
                job_id = p.seed_job()
                p.enqueue(job_id)
                p.wait(job_id)
        except Exception as exc:  # noqa: BLE001 - recorded as a failed "request"
            exception = exc
        events.request.fire(
            request_type="JOB",
            name="portfolio_analysis_end_to_end",
            response_time=(time.perf_counter() - start) * 1000,
            response_length=0,
            exception=exception,
            context={},
        )
