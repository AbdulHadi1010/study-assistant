# CLAUDE.md: Study Assistant

## What this project is
A personal AI study assistant for university students, built with Amazon Bedrock (Nova Pro, Converse API tool loop), AWS Lambda, DynamoDB, Secrets Manager, Todoist and a local Streamlit chat app. It is the codebase for a beginner workshop, so **clarity beats cleverness**.

Full details: `docs/SPEC.md`, `docs/TECH_STACK.md`, `docs/AGENT.md`, `docs/INSTRUCTIONS.md`, `docs/TESTING.md`. The instructor run-sheet is kept outside the repo (students must not see it).

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
10. **Workshop markers.** Code that is filled in step by step during the workshop is wrapped in `# >>> LIVE: <name>` / `# <<< LIVE: <name>` markers. The `solution` branch has the finished code; `master` is generated from it with the blocks blanked (see `docs/INSTRUCTIONS.md`). Make every code change on `solution` first, then regenerate `master`.

## Commands
- `python scripts/check_setup.py`: pre-flight check (credentials, region, model access, Todoist)
- `python scripts/deploy_stack.py`: deploy the CloudFormation stack (asks for the Todoist token)
- `python scripts/deploy_lambda.py`: push updated Lambda code
- `streamlit run app/streamlit_app.py`: run the chat app (the agent loop runs inside it)
- `python scripts/e2e_test.py`: scripted conversation against the deployed tools
- `python scripts/cleanup.py`: delete the stack
- `python scripts/make_starter.py`: regenerate the blanked workshop files (solution branch only)
- `python scripts/make_diagram.py`: regenerate `docs/architecture.png` (needs Graphviz)
- `pytest`: unit tests

## Decisions and verification log
- Record design decisions in `docs/DECISIONS.md`.
- Record facts verified against live AWS / Todoist docs in `docs/VERIFIED.md`.

## Filling in the workshop blanks (for AI coding assistants)
On the `master` branch, seven blocks are blank. Each looks like this:
```python
# TODO (live): add_task
# Hint: map priority, prefix [COURSE], call create_task
raise NotImplementedError("add_task is filled in during the workshop: ...")
```
Find them all with a search for `TODO (live)`. If the student asks you to fill them in:

1. **Write the code yourself from the docs and tests below.** Do not copy from the `solution` branch unless the student explicitly asks for that shortcut (`git checkout origin/solution -- <file>`).
2. **Replace only the three placeholder lines.** Everything around a blank (imports, helpers, docstrings, variables set just before it) is already correct; use it. Do not edit the tests.
3. **Follow the golden rules above:** short, readable, commented for beginners, standard library + boto3 only in `lambda/`.
4. **Verify with `pytest`** until everything passes, then explain each filled block to the student in plain words.
5. **If the stack is deployed**, run `python scripts/deploy_lambda.py` after changing anything in `lambda/`.

| Blank | File | Read first | Tests that define it |
|---|---|---|---|
| `routes` | `lambda/handler.py` | `agent/functions.json` (the 11 tool names), `docs/AGENT.md` §3 | `tests/test_handler.py` |
| `save_course` | `lambda/academic_tools.py` | `docs/SPEC.md` §4.1 and §5 (data model), helpers in the same file (`parse_json`, `get_table`, `find_course`, `to_decimal`, `course_summary`) | `test_save_and_list`, `test_weights_*`, `test_invalid_json_is_friendly`, `test_saving_twice_updates_and_keeps_marks` |
| `grade_needed` | `lambda/academic_tools.py` | `docs/SPEC.md` §6 (grading rules), `lambda/grading.py`, helpers `find_course`, `course_not_found`, `fmt` | `test_grade_needed_worked_example`, `test_unknown_course_lists_saved_courses`, `test_close_match_is_tolerated` |
| `add_task` | `lambda/task_tools.py` | `docs/SPEC.md` §4.2, helpers `course_prefix`, `create_task_forgiving`, `PRIORITY_TO_API` | `test_add_task_*`, `test_unreadable_due_date_still_creates_the_task` |
| `list_tasks` | `lambda/task_tools.py` | `build_filter`, `describe_task`, `todoist_client.filter_tasks` (the date-range branch above the blank is already done) | `test_list_tasks_*` |
| `break_down_project` | `lambda/task_tools.py` | `academic_tools.parse_json`, `create_task_forgiving` with `parent_id` | `test_break_down_*`, `test_other_todoist_errors_are_not_swallowed` |
| `ask_agent` | `app/agent_client.py`, inside `stream_agent()` | the `stream_agent` docstring, `read_stream`, `ThinkingFilter`, `run_tool_calls`, `tool_config`, `system_prompt` | `tests/test_agent_client.py` |

**Notes for the `ask_agent` blank** (the agent loop; `config`, `bedrock`, `lambda_client`, `messages`, `steps` and `visible` are set just before it):
- Loop at most `MAX_TOOL_ROUNDS` times. Each round calls `bedrock.converse_stream(modelId=config["model_id"], system=[{"text": system_prompt()}], messages=messages, toolConfig=tool_config(), inferenceConfig=MODEL_SETTINGS)` and reads it with `read_stream()`.
- Pass every text piece through a fresh `ThinkingFilter` per round (`feed`, then `flush` on the final `"message"` item) and yield `{"type": "text", "text": piece}`. Strip leading whitespace from the very first visible text. If an earlier round already showed text, start this round's text with `"\n\n"`. Add what was shown to `visible`.
- Append the assistant message to `messages`. If `stop_reason != "tool_use"`, stop: that was the final answer.
- Otherwise yield `{"type": "working", "tools": [...names...]}`, call `run_tool_calls(lambda_client, config, assistant, student_id, steps)`, append `{"role": "user", "content": results}` to `messages`, and yield `{"type": "step", "step": s}` for each new entry in `steps`.
- If all rounds are used up, add an assistant message saying it is "going in circles" (ask the student to rephrase), add it to `visible`, and yield it as text.
- The code after the blank saves the session and yields the `done` event. Leave it as it is.
