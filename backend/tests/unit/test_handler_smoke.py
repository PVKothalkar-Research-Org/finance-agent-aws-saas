"""Run each real Lambda handler end to end with a fake LLM runner and fake database.

Each agent folder has modules with identical names (agent.py, lambda_handler.py, templates.py), so every
handler runs in its own interpreter with the agent folder as the working directory.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("litellm")
pytest.importorskip("agents")
pytest.importorskip("langfuse")

BACKEND = Path(__file__).resolve().parents[2]
SMOKE = BACKEND / "tests" / "smoke"


def run(script: str, agent: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SMOKE / script), *args], cwd=BACKEND / agent,
                          capture_output=True, text=True, timeout=180)


@pytest.mark.parametrize("agent", ["retirement", "reporter", "charter"])
def test_specialist_handler_status_codes_and_persistence(agent):
    result = run("handler_smoke.py", agent, agent)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{agent} OK" in result.stdout


def test_planner_uses_injected_mock_invoker_and_updates_job_status():
    result = run("planner_smoke.py", "planner")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "planner OK" in result.stdout
