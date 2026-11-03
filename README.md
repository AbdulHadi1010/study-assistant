# Study Assistant

A personal AI study assistant built on Amazon Bedrock (Nova Pro + the Converse API tool loop), AWS Lambda, DynamoDB and Todoist. Chat with it to save your courses, check what grade you need, and manage your real Todoist to-do list.

![Architecture](docs/architecture.png)

More detail: [docs/architecture.md](docs/architecture.md).

## Two branches
| Branch | What is in it | Who uses it |
|---|---|---|
| `master` | The workshop version. Everything works except a few blanks marked `# TODO (live)` that we fill in together. | Clone this for the workshop |
| `solution` | The finished, working app. | Catching up, or using the app on your own |

You never type code in the workshop. Each blank is filled by copying the finished file from `solution`:
```
git checkout origin/solution -- lambda/task_tools.py
```
That same command is how you catch up if you fall behind.

## Before the workshop (about 30 minutes, at home)
All commands work the same in PowerShell, macOS and Linux unless shown otherwise.

**1. Install the tools**
- [Python 3.10+](https://www.python.org/downloads/) (on Windows tick "Add python.exe to PATH")
- [Git](https://git-scm.com/downloads)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

**2. Create an IAM user for the workshop** (AWS console)
1. IAM -> Users -> **Create user**, name it `study-assistant-workshop`.
2. Permissions: **Attach policies directly** -> **Create policy** -> JSON tab -> paste the contents of [docs/iam-policy.json](docs/iam-policy.json) -> name it `StudyAssistantWorkshop` -> create, then attach it to the user.
3. Open the user -> Security credentials -> **Create access key** -> "Command Line Interface (CLI)". Keep the two keys for the next step.

The policy only allows what this project needs (its own stack, table, Lambda, secret, plus Bedrock and Polly).

**3. Configure the AWS CLI**
```
aws configure
```
Paste the two keys, region `us-east-1`, output `json`.

**4. Get a Todoist token**
Create a free [Todoist](https://todoist.com) account -> Settings -> Integrations -> Developer -> copy the API token. You will paste it once, during the workshop.

**5. Clone and install**
```
git clone https://github.com/AbdulHadi1010/study-assistant.git
cd study-assistant
python -m venv .venv
```
Activate it, Windows: `.venv\Scripts\activate`; macOS/Linux: `source .venv/bin/activate`. Then:
```
pip install -r requirements-dev.txt
```

**6. Check everything**
```
python scripts/check_setup.py
```
Fix anything marked ❌ (each line tells you how) until it is all ✅.

## During the workshop
| Step | Command | What it does |
|---|---|---|
| 1 | `python scripts/deploy_stack.py` | Creates the DynamoDB table, the Todoist secret, the Lambda and its role (asks for your Todoist token, input hidden) |
| 2 | `pytest` | Shows what is still blank (red tests) |
| 3 | `git checkout origin/solution -- lambda/handler.py lambda/academic_tools.py lambda/task_tools.py` | Fills in the tools (we do these one file at a time) |
| 4 | `python scripts/deploy_lambda.py` | Pushes the finished tools to AWS |
| 5 | `git checkout origin/solution -- app/agent_client.py` | Fills in the agent loop |
| 6 | `streamlit run app/streamlit_app.py` | Opens the chat app |
| 7 | `python scripts/cleanup.py` | **Deletes everything** so nothing keeps costing money |

Try: *"My courses are OS (3 credits: quizzes 15, assignments 15, midterm 30, final 40)."* Then record marks, ask *"What do I need in the OS final to get an A-?"*, and *"Add my DB assignment due next Friday, high priority."* Turn on **Show agent reasoning** to watch the agent pick tools. Turn on **Speak replies (Polly)** to hear the answers.

> **Why no Bedrock Agent?** AWS closed Bedrock Agents Classic to accounts with no recent agent usage (July 2026), so `CreateAgent` fails on new accounts. We run the same reason-act-observe loop ourselves with the Converse API instead; see `stream_agent()` in `app/agent_client.py`.

## Troubleshooting
| Problem | Fix |
|---|---|
| `NotImplementedError: ... filled in during the workshop` | Run the `git checkout origin/solution -- <file>` command it prints |
| `config.json not found` / tools not deployed | Run `python scripts/deploy_stack.py` |
| `No AWS credentials found` | `aws configure` |
| Access denied / model access | Bedrock console -> Model access -> enable Amazon Nova Pro in `us-east-1` |
| `lambda:InvokeFunction` access denied | Your IAM user is missing the policy from `docs/iam-policy.json` |
| Throttling | Wait a few seconds and retry |
| "Your Todoist token looks invalid" | Re-run `python scripts/deploy_stack.py` and paste a fresh token |
| Region mismatch | Make `config.json` and `aws configure get region` agree |
| Changed Lambda code but nothing happens | `python scripts/deploy_lambda.py` |
| Changed agent instructions or `functions.json` | Nothing to deploy: just restart the app |

## Repository map
| Folder | What is in it |
|---|---|
| `lambda/` | The tools (runs in AWS Lambda): courses and grades in DynamoDB, tasks in Todoist |
| `agent/` | What the model is told: system prompt and the list of tools |
| `app/` | Streamlit chat UI and the agent loop (runs on your laptop) |
| `infra/` | CloudFormation template: everything AWS creates for you |
| `scripts/` | Deploy, check, test and clean-up scripts |
| `tests/` | Unit tests (no AWS needed) |
| `docs/` | Spec, design decisions, IAM policy, architecture diagram |

## Extend it yourself
`record_absence` and `daily_brief` are already coded in the Lambda; wire them into your own prompts. Next ideas: voice input (Transcribe), Google Calendar / Google Tasks via OAuth, deploying Streamlit, Bedrock Guardrails, agent long-term memory.
