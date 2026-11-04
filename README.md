# Finance Agent AWS SaaS

Multi-agent, serverless financial-planning platform on AWS. Users record investment accounts and positions; a planner agent orchestrates specialist agents (tagger, reporter, charter, retirement) that produce a written report, charts and a Monte Carlo retirement projection. A researcher agent maintains a vector knowledge base of market research.

## Components

| Directory | Purpose |
|---|---|
| `backend/common` | Shared package `agent_common`: settings, retry policy, Lambda invoker, portfolio models, handler base |
| `backend/database` | Aurora Serverless v2 (Data API) client, typed rows, repositories, schemas |
| `backend/planner` | Orchestrator Lambda (SQS-triggered) |
| `backend/tagger` | Instrument classification agent |
| `backend/reporter` | Portfolio report agent |
| `backend/charter` | Chart-data agent |
| `backend/retirement` | Retirement projection agent |
| `backend/researcher` | Market research agent (container service) |
| `backend/ingest` | Document ingestion Lambda (S3 Vectors, SageMaker embeddings) |
| `backend/api` | FastAPI backend for the frontend |
| `backend/tests`, `backend/loadtest` | Unit, integration, smoke and load tests |
| `frontend` | Next.js application with Clerk authentication |
| `iam` | Deployer IAM policy and setup commands |
| `terraform` | Eight independent stacks, each with its own state and `terraform.tfvars` |
| `scripts` | Deployment, local run and teardown scripts |
| `docs` | Architecture, design (OOAD, data flow), diagrams, changelog |

## Prerequisites

AWS account with Bedrock model access in the target region(s), AWS CLI configured, Terraform, [uv](https://docs.astral.sh/uv/), Docker (Lambda packaging), Node.js, a Clerk application, and an OpenAI API key (agent tracing).

All Python is run through uv (`uv sync`, `uv run`); each backend directory is a uv project.

## Deployment order

Each stack is independent: copy `terraform.tfvars.example` to `terraform.tfvars`, set the values, then `terraform init && terraform apply`. Apply in numeric order; values from earlier stacks (`terraform output`) go into the root `.env` (see `.env.example`) and later `terraform.tfvars` files. Details per stack are in [terraform/README.md](terraform/README.md).

| Step | Stack | Deploys | Additional actions |
|---|---|---|---|
| 1 | IAM | Deployer policy for the services used by the stacks ([iam/](iam/README.md)) | Create the group and attach `iam/finance-agent-aws-saas-deployer-policy.json`; `aws configure` for that user; enable Bedrock model access in the chosen region(s) |
| 2 | `terraform/2_sagemaker` | Embedding endpoint (SageMaker Serverless) | Record endpoint name in `.env` |
| 3 | `terraform/3_ingestion` | S3 Vectors, ingest Lambda, API Gateway with API key | In the S3 console create vector bucket `finance-agent-aws-saas-vectors-<account-id>` with index `financial-research` (384 dimensions, cosine); build the Lambda zip with `uv run package.py` in `backend/ingest`; record endpoint, key and bucket in `.env` |
| 4 | `terraform/4_researcher` | Researcher container-image Lambda with function URL, ECR repository, scheduler | `uv run deploy.py` in `backend/researcher` applies the ECR repository, builds and pushes the image, then applies the stack; set the researcher region and model in `terraform.tfvars` |
| 5 | `terraform/5_database` | Aurora Serverless v2 with Data API | `uv run run_migrations.py`, `uv run seed_data.py` (22 reference ETFs) and optionally `uv run create_test_data.py` (demo user `test_user_001`) in `backend/database`; record cluster and secret ARNs in `.env` |
| 6 | `terraform/6_agents` | Planner, tagger, reporter, charter, retirement Lambdas, SQS queue and DLQ | Build each package with `uv run package_docker.py` (Docker running), then `backend/deploy_all_lambdas.py` |
| 7 | `terraform/7_frontend` | API Lambda, API Gateway, S3, CloudFront | Create a Clerk application; set `frontend/.env.local` and `CLERK_JWKS_URL`; deploy the site with `scripts/deploy.py` |
| 8 | `terraform/8_enterprise` | CloudWatch dashboards and alarms | Optional Langfuse keys for tracing |

Local run of API and frontend: `scripts/run_local.py`. Architecture and design: [docs/](docs/README.md).

## Agent implementation notes

- Framework: OpenAI Agents SDK (`openai-agents`, `from agents import Agent, Runner, trace`) with LiteLLM routing to AWS Bedrock: `LitellmModel(model=f"bedrock/{model_id}")`.
- LiteLLM requires `AWS_REGION_NAME` to be set (done by `agent_common.configure_bedrock_region`).
- With LiteLLM and Bedrock an agent uses either structured outputs or tools, not both.
- Default model is set by `BEDROCK_MODEL_ID`; Amazon Nova Pro is a lower-rate-limit-risk alternative and needs an inference profile and model access in each region used.
- Per-agent layout: `agent.py` (agent construction), `lambda_handler.py` (entry point), `templates.py` (prompts), plus pure logic modules (`simulation.py`, `orchestration.py`, `metrics.py`, `analysis.py`).

## Testing

```bash
cd backend
uv sync --group dev
uv run pytest                                    # offline unit tests
(cd common && uv run pytest)                     # shared package tests
uv run ruff check common database planner retirement reporter charter tagger tests loadtest
RUN_INTEGRATION=1 uv run pytest -m integration   # against deployed Lambdas / Aurora
LOAD_MODE=mock uv run python loadtest/run_profile.py --duration 10   # load profile (p50/p95/error rate)
```

Per-agent scripts: `test_simple.py` (local, `MOCK_LAMBDAS=true`) and `test_full.py` (deployed Lambdas).

## Troubleshooting

| Symptom | Check |
|---|---|
| `package_docker.py` fails | Docker running; directory shared with Docker (File Sharing) |
| Bedrock access denied / model not found | Model access granted in the region; inference-profile permissions for all regions it routes to; `AWS_REGION_NAME` |
| `terraform apply` fails | `terraform.tfvars` present and complete; outputs from earlier stacks copied in |
| Lambda errors | CloudWatch logs `/aws/lambda/finance-agent-aws-saas-<agent>`; env vars; IAM role; package built for linux/amd64 |
| Aurora connection errors | Cluster `available`; Data API enabled; ARNs match `terraform output` in `5_database` |

## Teardown

```bash
for d in 8_enterprise 7_frontend 6_agents 5_database 4_researcher 3_ingestion 2_sagemaker; do (cd terraform/$d && terraform destroy); done
```

## License and attribution

MIT License (see [LICENSE](LICENSE)). The original copyright notice must be retained under the terms of the license; this repository is a modified derivative of an openly licensed base project.
