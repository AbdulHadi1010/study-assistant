# TECH_STACK.md: Study Assistant

## AWS services
| Service | Use | Notes |
|---|---|---|
| Amazon Bedrock Agents | The assistant's brain: ReAct reasoning, tool selection, session memory | Created by `scripts/setup_agent.py` (boto3 `bedrock-agent`), **not** CloudFormation, because it is built live in the workshop |
| Amazon Bedrock model | Amazon Nova Pro (default), Nova Lite (cheaper fallback) | Configurable. Verify which model / inference profile IDs Bedrock Agents supports in the region before coding. Agents may require a cross-region inference profile ID (e.g., `us.amazon.nova-pro-v1:0`); check and record in `docs/VERIFIED.md`. If a newer Nova generation is available and supported for agents, prefer it and note why. |
| AWS Lambda | All tool logic (one function, two action groups) | Python 3.12 runtime (or the newest Python runtime Lambda supports; verify). Not in a VPC (needs internet for Todoist). Timeout 30s, memory 256 MB. |
| Amazon DynamoDB | Student academic profile | On-demand (PAY_PER_REQUEST) |
| AWS Secrets Manager | Todoist API token | No fixed secret name (let CloudFormation generate it) so the stack can be deleted and recreated without name clashes |
| AWS CloudFormation | All infrastructure except the agent | Single template `infra/template.yaml`, deployed with `aws cloudformation deploy` via a Python wrapper |
| Amazon CloudWatch Logs | Lambda logs | Log group created in the template with 7-day retention so cleanup removes it |
| Amazon Polly (bonus) | Speak replies in Streamlit | `synthesize_speech`, neural voice, MP3 |
| IAM | Lambda execution role, Bedrock agent service role | Both in the template, least privilege |

## External service
| Service | Use | Notes |
|---|---|---|
| Todoist | The student's real to-do list | Personal API token (Settings → Integrations → Developer). Free plan is enough. **Verify the current API version and base URL** (Todoist moved to a unified API v1; the older REST v2 may be deprecated). Use natural-language `due_string` for due dates, priority 1 to 4 (4 = urgent in the API), `parent_id` for subtasks, and the filter endpoint for listing. |

## Languages and libraries
| Where | Allowed | Not allowed |
|---|---|---|
| Lambda | Python standard library, boto3 (from runtime) | `requests`, any pip package needing a Lambda layer |
| Scripts | Python 3.10+, boto3 | Shell scripts, `zip` CLI, `jq` |
| Frontend | Streamlit (current), boto3 | Other UI frameworks, `python-dotenv` (use a JSON config file) |
| Dev only | pytest, moto (DynamoDB mocking) | Anything else without asking |

Pin versions with `>=` minimums in `requirements.txt` (student) and `requirements-dev.txt` (instructor/tests).

## Configuration
A single `config.json` at the repo root, written and updated by the scripts (never committed; provide `config.example.json`):
```json
{
  "region": "us-east-1",
  "stack_name": "study-assistant",
  "model_id": "<verified inference profile or model id>",
  "agent_id": "",
  "agent_alias_id": "",
  "lambda_function_name": "",
  "table_name": "",
  "agent_role_arn": "",
  "polly_voice": "Joanna"
}
```

## Student prerequisites (already handled by the organiser)
- AWS account with credits, spend limit, IAM user credentials configured in the AWS CLI
- Bedrock model access granted for the chosen model in the chosen region
- Python 3.10+, boto3, Streamlit installed
- **Added by us:** a free Todoist account and its API token

## Out of scope
- Deploying the Streamlit app to the cloud
- Knowledge Bases / RAG (OpenSearch Serverless cost risk for students)
- OAuth integrations (Google Tasks, Microsoft To Do): mention as "next steps" only
- Voice input (speech to text): mention as "next steps" only
