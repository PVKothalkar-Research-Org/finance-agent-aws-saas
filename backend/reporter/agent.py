"""
Report Writer Agent - generates portfolio analysis narratives.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_common import Portfolio, Settings, UserProfile, configure_bedrock_region, litellm_model_name
from agent_common.settings import DEFAULT_PREFIX
from agents import RunContextWrapper, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from metrics import format_portfolio_for_analysis

logger = logging.getLogger()

VECTOR_BUCKET_PREFIX = f"{DEFAULT_PREFIX}-vectors"


@dataclass
class ReporterContext:
    """Context for the Reporter agent."""

    job_id: str
    portfolio: Portfolio
    user: UserProfile
    settings: Settings
    db: Any | None = None  # Database connection (optional for testing)


@function_tool
async def get_market_insights(
    wrapper: RunContextWrapper[ReporterContext], symbols: list[str]
) -> str:
    """
    Retrieve market insights from S3 Vectors knowledge base.

    Args:
        wrapper: Context wrapper with job_id and database
        symbols: List of symbols to get insights for

    Returns:
        Relevant market context and insights
    """
    ctx = wrapper.context
    try:
        import boto3

        # Get account ID
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        bucket = f"{VECTOR_BUCKET_PREFIX}-{account_id}"

        # Get embeddings
        sagemaker_region = ctx.settings.default_aws_region
        sagemaker = boto3.client("sagemaker-runtime", region_name=sagemaker_region)
        endpoint_name = os.getenv("SAGEMAKER_ENDPOINT", f"{DEFAULT_PREFIX}-embedding-endpoint")
        query = f"market analysis {' '.join(symbols[:5])}" if symbols else "market outlook"

        response = sagemaker.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps({"inputs": query}),
        )

        result = json.loads(response["Body"].read().decode())
        # Extract embedding (handle nested arrays)
        if isinstance(result, list) and result:
            embedding = result[0][0] if isinstance(result[0], list) else result[0]
        else:
            embedding = result

        # Search vectors
        s3v = boto3.client("s3vectors", region_name=sagemaker_region)
        response = s3v.query_vectors(
            vectorBucketName=bucket,
            indexName="financial-research",
            queryVector={"float32": embedding},
            topK=3,
            returnMetadata=True,
        )

        # Format insights
        insights = []
        for vector in response.get("vectors", []):
            metadata = vector.get("metadata", {})
            text = metadata.get("text", "")[:200]
            if text:
                company = metadata.get("company_name", "")
                prefix = f"{company}: " if company else "- "
                insights.append(f"{prefix}{text}...")

        if insights:
            return "Market Insights:\n" + "\n".join(insights)
        else:
            return "Market insights unavailable - proceeding with standard analysis."

    except Exception as e:
        logger.warning(f"Reporter: Could not retrieve market insights: {e}")
        return "Market insights unavailable - proceeding with standard analysis."


def create_agent(
    job_id: str, portfolio: Portfolio, user: UserProfile, settings: Settings, db: Any | None = None
) -> tuple[LitellmModel, list[Any], str, ReporterContext]:
    """Create the reporter agent with tools and context."""
    configure_bedrock_region(settings)
    model = LitellmModel(model=litellm_model_name(settings))
    context = ReporterContext(job_id=job_id, portfolio=portfolio, user=user, settings=settings, db=db)
    tools = [get_market_insights]  # report is saved by the Lambda handler
    portfolio_summary = format_portfolio_for_analysis(portfolio, user)

    # Create task
    task = f"""Analyze this investment portfolio and write a comprehensive report.

{portfolio_summary}

Your task:
1. First, get market insights for the top holdings using get_market_insights()
2. Analyze the portfolio's current state, strengths, and weaknesses
3. Generate a detailed, professional analysis report in markdown format

The report should include:
- Executive Summary
- Portfolio Composition Analysis
- Risk Assessment
- Diversification Analysis
- Retirement Readiness (based on user goals)
- Recommendations
- Market Context (from insights)

Provide your complete analysis as the final output in clear markdown format.
Make the report informative yet accessible to a retail investor."""

    return model, tools, task, context
