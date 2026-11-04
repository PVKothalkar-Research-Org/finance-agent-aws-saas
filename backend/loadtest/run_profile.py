"""Run the 10 / 50 / 100 concurrent-job profile and write a p50 / p95 / error-rate report.

    uv run python loadtest/run_profile.py                  # real AWS (LOAD_MODE=real)
    LOAD_MODE=mock uv run python loadtest/run_profile.py --duration 15   # local validation

Output: loadtest/results/<stage>_stats.csv plus loadtest/results/summary.md
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STAGES = (10, 50, 100)


def run_stage(users: int, duration: int) -> dict[str, float]:
    prefix = RESULTS / f"c{users}"
    cmd = [
        sys.executable, "-m", "locust", "-f", str(HERE / "locustfile.py"), "--headless",
        "-u", str(users), "-r", str(users), "-t", f"{duration}s", "--csv", str(prefix), "--only-summary",
    ]
    print(f"\n=== {users} concurrent jobs for {duration}s ===", flush=True)
    subprocess.run(cmd, check=False, cwd=HERE.parent)
    with open(f"{prefix}_stats.csv", newline="") as fh:
        rows = {r["Name"]: r for r in csv.DictReader(fh)}
    row = rows.get("portfolio_analysis_end_to_end") or rows["Aggregated"]
    total, failed = int(row["Request Count"]), int(row["Failure Count"])
    return {
        "users": users, "jobs": total, "failures": failed,
        "error_rate_pct": round(100 * failed / total, 2) if total else 100.0,
        "p50_ms": float(row["50%"]), "p95_ms": float(row["95%"]), "max_ms": float(row["Max Response Time"]),
        "jobs_per_s": float(row["Requests/s"]),
    }


def write_summary(results: list[dict[str, float]]) -> Path:
    lines = ["| Concurrent jobs | Jobs | p50 (s) | p95 (s) | Max (s) | Error rate | Jobs/s |", "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['users']} | {r['jobs']} | {r['p50_ms'] / 1000:.2f} | {r['p95_ms'] / 1000:.2f} | "
                     f"{r['max_ms'] / 1000:.2f} | {r['error_rate_pct']}% | {r['jobs_per_s']:.2f} |")
    out = RESULTS / "summary.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=600, help="seconds per stage (real jobs take minutes)")
    parser.add_argument("--stages", type=int, nargs="+", default=list(STAGES))
    parser.add_argument("--max-error-rate", type=float, default=None, help="exit 1 if any stage exceeds this %%")
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    results = [run_stage(u, args.duration) for u in args.stages]
    write_summary(results)
    if args.max_error_rate is not None and any(r["error_rate_pct"] > args.max_error_rate for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
