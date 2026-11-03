# INSTRUCTIONS.md: How to Build It

## 1. Repository layout (target)

```
study-assistant/
├── README.md                    # student-facing: prerequisites, step-by-step, troubleshooting
├── CLAUDE.md  AGENTS.md          # rules for AI coding assistants (same content)
├── config.example.json
├── requirements.txt             # boto3, streamlit
├── requirements-dev.txt         # + pytest, moto
├── .gitignore                   # config.json, build/, __pycache__, .venv
├── infra/
│   └── template.yaml            # CloudFormation: table, secret, roles, Lambda, log group, permission
├── lambda/
│   ├── handler.py               # entry point: parse event, route to tool, build response
│   ├── academic_tools.py        # save_course, list_courses, record_marks, grade_needed, calculate_gpa, record_absence
│   ├── task_tools.py            # add_task, list_tasks, complete_task, break_down_project, daily_brief
│   ├── todoist_client.py        # tiny urllib wrapper + token from Secrets Manager (cached)
│   ├── grading.py               # grade points, thresholds, maths (pure functions)
│   └── bedrock_io.py            # read parameters from the event, build the response
├── agent/
│   ├── agent_config.py          # name, instructions, TTL
│   └── functions.json           # action groups + function schemas (from AGENT.md)
├── app/
│   ├── streamlit_app.py         # chat UI
│   └── agent_client.py          # invoke_agent + trace parsing + Polly helper
├── scripts/
│   ├── deploy_stack.py          # cloudformation deploy, writes outputs to config.json
│   ├── deploy_lambda.py         # zip lambda/ in memory, update_function_code, wait
│   ├── setup_agent.py           # create/update agent, action groups, prepare, alias
│   ├── check_setup.py           # pre-flight: credentials, region, model access, Todoist token
│   ├── e2e_test.py              # acceptance conversation
│   ├── cleanup.py               # delete agent, then delete stack, wait
│   └── make_starter.py          # generates starter/ from solution code using LIVE markers
├── tests/
│   ├── events/                  # sample Bedrock events
│   ├── test_grading.py
│   ├── test_academic_tools.py   # moto DynamoDB
│   ├── test_task_tools.py       # mocked Todoist HTTP
│   └── test_handler.py          # routing + response format
└── docs/
    ├── SPEC.md  TECH_STACK.md  AGENT.md  INSTRUCTIONS.md  TESTING.md  PROMPT.md
    ├── VERIFIED.md  DECISIONS.md
    └── architecture.md + architecture.png   # diagram (scripts/make_diagram.py) + ReAct explanation
```

## 2. Build phases (in order)

### Phase 0: Verify
Run the checks listed in `PROMPT.md` step 2. Write `docs/VERIFIED.md` before writing AWS code.

### Phase 1: Pure logic
`lambda/grading.py` + `tests/test_grading.py`. All grade maths and edge cases from `SPEC.md` §6. No AWS imports.

### Phase 2: Lambda tools
`bedrock_io.py`, `academic_tools.py`, `todoist_client.py`, `task_tools.py`, `handler.py` + unit tests (moto for DynamoDB, monkeypatched `urllib` for Todoist). Routing is a simple dict `{function_name: callable}`, readable for students.

### Phase 3: Infrastructure
`infra/template.yaml`:
- Parameter `TodoistToken` (`NoEcho: true`)
- DynamoDB table (PK `student_id`, SK `course_name`, on-demand)
- Secrets Manager secret holding the token (generated name)
- Lambda execution role: `dynamodb:GetItem/PutItem/UpdateItem/Query` on the table ARN, `secretsmanager:GetSecretValue` on the secret ARN, logs to its log group
- Log group `/aws/lambda/<function>` with 7-day retention
- Lambda function with inline placeholder code (real code pushed by `deploy_lambda.py`), env vars `TABLE_NAME`, `TODOIST_SECRET_ARN`
- Lambda permission: principal `bedrock.amazonaws.com`, `SourceAccount` = account, `SourceArn` = `arn:aws:bedrock:<region>:<account>:agent/*`
- Bedrock agent service role: trust `bedrock.amazonaws.com` with `aws:SourceAccount` condition; allow `bedrock:InvokeModel` (+ `bedrock:GetInferenceProfile` / profile and underlying model ARNs as required; verify)
- Outputs: table name, Lambda name + ARN, agent role ARN

`scripts/deploy_stack.py`: prompts for the Todoist token (hidden input via `getpass`) on first deploy, reuses the existing parameter on later deploys, runs the deploy with `CAPABILITY_NAMED_IAM`, waits, writes outputs to `config.json`, then calls `deploy_lambda.py`.

### Phase 4: Agent
`agent/functions.json` exactly matching `AGENT.md`. `scripts/setup_agent.py`:
- create the agent if `agent_id` is empty, else update it
- create or update both action groups pointing at the Lambda ARN; enable `AMAZON.UserInput`
- `prepare_agent`, poll until `PREPARED`
- create or update alias `live`, poll until `PREPARED`
- save IDs to `config.json`; print a success message with next steps
- idempotent; clear messages for common errors (model access denied, role not yet propagated: retry with backoff)

### Phase 5: Frontend
`app/agent_client.py`: `ask_agent(message, session_id, student_id, show_trace) -> (reply_text, trace_steps)` using `bedrock-agent-runtime.invoke_agent` with `enableTrace`, reading the event stream (`chunk` bytes + `trace` events). Plus `speak(text) -> bytes` using Polly.

`app/streamlit_app.py`: as in `SPEC.md` §4.4. Reads `config.json`; if missing, shows "Run scripts/setup_agent.py first".

### Phase 6: Scripts and docs
`check_setup.py`, `e2e_test.py`, `cleanup.py`, `README.md` (student-facing; PowerShell and bash commands side by side), `docs/architecture.md`.

### Phase 7: Starter generation (two branches)
The repo has two branches:
- `solution`: the finished, working code (all tests pass).
- `master`: what students clone. Same files, but every LIVE block is blanked.

Nobody types code in the workshop. At each step students fill in a blank by copying the finished file from `solution` (`git checkout origin/solution -- lambda/task_tools.py`), and the instructor walks through it.

`scripts/make_starter.py` copies `lambda/`, `app/` and `agent/` into `starter/`, replacing every block between `# >>> LIVE: <name>` and `# <<< LIVE: <name>` with:

```python
# TODO (live): <name>
# Hint: <one-line hint from the marker, if given>
raise NotImplementedError("<name> is filled in during the workshop: git checkout origin/solution -- <folder>/<file>")
```

Markers may carry a hint: `# >>> LIVE: grade_needed | hint: earned so far vs remaining weight`. The starter must still import and pass `python -m py_compile`.

**Updating the code (maintainers).** Always change `solution` first, then regenerate `master`:
```
git switch solution
# edit, then: pytest
git commit -am "..."
python scripts/make_starter.py          # writes starter/ (git-ignored, so it survives the branch switch)
git switch master
git checkout solution -- .              # take every file from solution...
python -c "import shutil; [shutil.copytree(f'starter/{d}', d, dirs_exist_ok=True) for d in ('lambda', 'app', 'agent')]"
git rm -q scripts/make_starter.py tests/test_starter.py
git add -A
git commit -m "Regenerate workshop starter"
git push origin solution master
```
The `python -c` line puts the blanked files back over the finished ones. `make_starter.py` and `tests/test_starter.py` live only on `solution`.

**Blocks marked LIVE (filled in during the session):**
- `academic_tools.save_course`, `academic_tools.grade_needed` (body only)
- `task_tools.add_task`, `task_tools.list_tasks`, `task_tools.break_down_project` (body only)
- the routing dict in `handler.py`
- `agent_client.ask_agent` (the `invoke_agent` call and stream loop)

Everything else stays complete in the starter.

## 3. Coding conventions
- Python 3.10+ syntax, type hints on public functions, f-strings.
- Every module starts with a 3 to 6 line docstring: what it does and where it sits in the architecture.
- Functions under about 30 lines where possible.
- Constants in UPPER_CASE at the top of the module.
- `logging` (not `print`) in Lambda; `print` is fine in scripts.
- No global mutable state except cached boto3 clients and the cached Todoist token.

## 4. When you are done
- `pytest` passes.
- `python scripts/make_starter.py` runs; `starter/` compiles.
- After I approve a deploy: `check_setup.py`, `deploy_stack.py`, `setup_agent.py`, `e2e_test.py` all succeed; then `cleanup.py` leaves no resources (verify the stack is gone and the agent is deleted).
- Write a summary as described in `PROMPT.md`.
