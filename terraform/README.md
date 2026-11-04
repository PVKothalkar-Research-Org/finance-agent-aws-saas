# Terraform Infrastructure

Terraform configuration for Finance Agent AWS SaaS. Each stack is independent, with its own local state and its own `terraform.tfvars`.

## Stacks

| Directory | Resources |
|---|---|
| `2_sagemaker/` | SageMaker serverless embedding endpoint |
| `3_ingestion/` | S3 Vectors bucket, ingest Lambda, API Gateway with API key |
| `4_researcher/` | Researcher container-image Lambda with a function URL, ECR repository, scheduler Lambda and EventBridge schedule |
| `5_database/` | Aurora Serverless v2 PostgreSQL with Data API, Secrets Manager |
| `6_agents/` | Planner, tagger, reporter, charter and retirement Lambdas, SQS queue and dead-letter queue, package bucket |
| `7_frontend/` | API Lambda, API Gateway, S3, CloudFront |
| `8_enterprise/` | CloudWatch dashboards and alarms, monitoring |

## Design

**Independent stacks.** Each stack deploys, updates and is destroyed on its own. A mistake in one stack does not affect infrastructure deployed by another, and a later stack cannot be applied before the values it needs from earlier stacks are set.

**Local state.** No state bucket or lock table is required, so a stack can be applied immediately. State files (`*.tfstate`) are gitignored.

## Usage

Per stack:

```bash
cd terraform/<stack>               # for example 2_sagemaker
cp terraform.tfvars.example terraform.tfvars   # then set the values
terraform init                     # once per directory
terraform plan
terraform apply
terraform destroy                  # to remove the stack
```

Apply the stacks in numeric order. Values a stack needs from an earlier one are read with `terraform output` in the earlier directory and set in the later stack's `terraform.tfvars` or in the root `.env`.

## Environment variables

Some stacks read values from the root `.env`:

| Variable | Used by | Source |
|---|---|---|
| `OPENAI_API_KEY` | `4_researcher` | OpenAI account |
| `FINANCE_AGENT_AWS_SAAS_API_ENDPOINT`, `FINANCE_AGENT_AWS_SAAS_API_KEY` | `4_researcher` | `3_ingestion` outputs |
| `VECTOR_BUCKET` | `4_researcher` | `3_ingestion` outputs |
| `AURORA_CLUSTER_ARN`, `AURORA_SECRET_ARN` | `6_agents`, `7_frontend` | `5_database` outputs |
| `BEDROCK_MODEL_ID`, `BEDROCK_REGION` | `6_agents` | Bedrock model access in the chosen region |

## State management

- Each directory keeps its own `terraform.tfstate`, stored locally.
- Back up state files before significant changes.
- Resource names use the `finance-agent-aws-saas` prefix; applying over state created under a different prefix creates new resources.

## Troubleshooting

1. **Import existing resources:**
   ```bash
   terraform import <resource_type>.<resource_name> <resource_id>
   ```
2. **Missing values:** confirm `terraform.tfvars` exists and is complete, and that earlier stacks are applied and their outputs copied.
3. **Reset a stack:**
   ```bash
   terraform destroy
   rm -rf .terraform terraform.tfstate*
   terraform init
   ```
