# CLAUDE.md: Study Assistant

## What this project is
A personal AI study assistant for university students, built with Amazon Bedrock Agents, AWS Lambda, DynamoDB, Secrets Manager, Todoist and a local Streamlit chat app. It is the codebase for a beginner workshop, so **clarity beats cleverness**.

Full details: `docs/SPEC.md`, `docs/TECH_STACK.md`, `docs/AGENT.md`, `docs/INSTRUCTIONS.md`, `docs/TESTING.md`, `docs/WORKSHOP.md`.

## Audience
First- and second-year CS students who know basic Python. They have never written a Lambda or used Bedrock. Every file they open must be readable top to bottom.

## Golden rules
1. **Readable over clever.** Short functions, descriptive names, no metaclasses, decorators-of-decorators, or deep abstractions. One concept per function.
2. **Comment the why, not the what.** Each file starts with a short docstring explaining its role in the architecture. Comments explain AWS concepts students will not know (e.g., why Bedrock needs a resource-based permission on the Lambda).
3. **Zero extra runtime dependencies in Lambda.** Standard library + boto3 only (boto3 ships with the Lambda runtime). Use `urllib.request` for Todoist, not `requests`.
4. **Student machines need only:** Python, boto3, Streamlit, AWS CLI. Anything else is dev-only (`requirements-dev.txt`).
5. **Cross-platform.** All scripts are Python, use `pathlib`, and work on Windows PowerShell, macOS and Linux. Never rely on `zip`, `sed`, `jq`, or bash-only syntax.
6. **No hardcoded secrets, account IDs or regions.** Region comes from config; the Todoist token lives in Secrets Manager.
7. **Least-privilege IAM.** Every policy scoped to the specific resource ARNs created by the stack.
8. **Friendly errors.** Tools never crash the agent: catch exceptions and return a clear text message the agent can relay ("I couldn't find a course called 'OS'. Your saved courses are: ...").
9. **Idempotent scripts.** Running setup or deploy twice must not break anything.
10. **Live-coding markers.** Code that will be typed live in the workshop is wrapped in `# >>> LIVE: <name>` / `# <<< LIVE: <name>` markers (see `docs/INSTRUCTIONS.md`).

## Commands (to be created)
- `python scripts/deploy_stack.py`: deploy the CloudFormation stack (asks for the Todoist token)
- `python scripts/deploy_lambda.py`: push updated Lambda code
- `python scripts/setup_agent.py`: create/update and prepare the Bedrock Agent + alias
- `streamlit run app/streamlit_app.py`: run the chat app
- `python scripts/e2e_test.py`: scripted conversation against the deployed agent
- `python scripts/cleanup.py`: delete the agent and the stack
- `pytest`: unit tests

## Decisions and verification log
- Record design decisions in `docs/DECISIONS.md`.
- Record facts verified against live AWS / Todoist docs in `docs/VERIFIED.md`.
