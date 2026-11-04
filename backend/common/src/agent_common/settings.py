"""Typed, immutable runtime configuration read once from the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_PREFIX = "finance-agent-aws-saas"
DEFAULT_MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration shared by all agents."""

    bedrock_model_id: str = DEFAULT_MODEL_ID
    bedrock_region: str = "us-west-2"
    default_aws_region: str = "us-east-1"
    tagger_function: str = f"{DEFAULT_PREFIX}-tagger"
    reporter_function: str = f"{DEFAULT_PREFIX}-reporter"
    charter_function: str = f"{DEFAULT_PREFIX}-charter"
    retirement_function: str = f"{DEFAULT_PREFIX}-retirement"
    mock_lambdas: bool = False
    default_years_until_retirement: int = 30
    default_target_retirement_income: float = 80_000.0


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from ``env`` (defaults to ``os.environ``)."""
    e = os.environ if env is None else env
    defaults = Settings()
    return Settings(
        bedrock_model_id=e.get("BEDROCK_MODEL_ID", defaults.bedrock_model_id),
        bedrock_region=e.get("BEDROCK_REGION", defaults.bedrock_region),
        default_aws_region=e.get("DEFAULT_AWS_REGION", defaults.default_aws_region),
        tagger_function=e.get("TAGGER_FUNCTION", defaults.tagger_function),
        reporter_function=e.get("REPORTER_FUNCTION", defaults.reporter_function),
        charter_function=e.get("CHARTER_FUNCTION", defaults.charter_function),
        retirement_function=e.get("RETIREMENT_FUNCTION", defaults.retirement_function),
        mock_lambdas=e.get("MOCK_LAMBDAS", "false").lower() == "true",
    )


def litellm_model_name(settings: Settings) -> str:
    """LiteLLM model string for Bedrock, e.g. ``bedrock/us.anthropic...``."""
    return f"bedrock/{settings.bedrock_model_id}"


def configure_bedrock_region(settings: Settings) -> None:
    """LiteLLM reads ``AWS_REGION_NAME``; set it from the typed settings."""
    os.environ["AWS_REGION_NAME"] = settings.bedrock_region
