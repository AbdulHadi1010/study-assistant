# TESTING.md: Tests and Definition of Done

## 1. Unit tests (no AWS, no internet, no cost)
Run with `pytest`. Use moto for DynamoDB and monkeypatch `urllib.request.urlopen` for Todoist.

### `test_grading.py`
- Grade points table matches `SPEC.md` §6.
- `percent_to_grade` at each boundary (e.g., 85.0 → A-, 84.99 → B+).
- `grade_needed`: the worked example below returns 90.0%.
- Target already secured → "secured" result; impossible target → best achievable grade.
- All components graded → final % and grade.
- GPA weighted correctly; courses without marks or projection are skipped and reported.

**Worked example (must pass):** OS weights quizzes 15, assignments 15, midterm 30, final 40. Marks 12/15, 13/15, 24/30. Earned = 12 + 13 + 24 = 49. Remaining weight = 40. Target A- (85) → (85 − 49) / 40 × 100 = **90.0%** on the final.

### `test_academic_tools.py`
- `save_course` validates weights sum to 100 (allow ±0.5) and rejects invalid JSON with a friendly message.
- Saving the same course twice updates it (case-insensitive name).
- `record_marks` rejects unknown components and `obtained > total`.
- Unknown course returns the list of saved courses.
- Data is isolated by `student_id`.

### `test_task_tools.py`
- `add_task` sends the correct payload (title prefix `[OS]`, `due_string`, priority mapping).
- `list_tasks` maps `week` / `today` / `overdue` / course name to the right filter query.
- `complete_task`: single match closes it; multiple matches closes none and lists them; no match is a friendly message.
- `break_down_project` creates one parent and N subtasks with `parent_id`; invalid `steps` JSON gives a friendly message.
- HTTP 401 → "Your Todoist token looks invalid"; timeout → friendly retry message.
- The token never appears in logs or responses.

### `test_handler.py`
- Uses `tests/events/sample_event.json` (verified shape).
- Routes to the correct function; unknown function gives a friendly error.
- Response format matches the verified function-details format, echoing `actionGroup` and `function` and passing `sessionAttributes` through.
- `student_id` read from session attributes; defaults to `"me"`.
- An exception inside a tool still returns a valid response.

## 2. Starter checks
- `python scripts/make_starter.py` succeeds.
- Every file in `starter/` compiles (`py_compile`).
- Each LIVE block in the solution has a matching TODO in the starter, and nothing else differs.

## 3. Pre-flight (`scripts/check_setup.py`)
Prints ✅/❌ with a fix hint for each:
- AWS credentials work (`sts get-caller-identity`), and the account ID is shown
- Region set and matches `config.json`
- Bedrock model access for `model_id` (a tiny `converse` call)
- Todoist token valid (only if available locally, e.g., entered at the prompt; never stored in `config.json`)
- Python and library versions

## 4. End-to-end (`scripts/e2e_test.py`, after deploy, costs a few cents)
- Runs the 10 acceptance steps from `SPEC.md` §8 in one session with `student_id = "e2e-test"`.
- Prints each user message, the agent reply, and the tools invoked (from the trace).
- Asserts the expected tool was called for each step; for Todoist steps, checks via the Todoist API that the task exists or is closed.
- Cleans up its own Todoist tasks and DynamoDB items at the end.
- Exit code 0 only if all steps pass.

## 5. Manual UI check
- `streamlit run app/streamlit_app.py` opens; the conversation works; the reasoning toggle shows tool calls; "New conversation" resets context; the Polly toggle plays audio.
- Missing `config.json` and missing credentials show friendly guidance.

## 6. Definition of done
- [ ] `docs/VERIFIED.md` lists every external fact checked, with sources
- [ ] All unit tests pass
- [ ] Starter generated and compiles
- [ ] Deploy → agent setup → e2e test passes on a clean account/region
- [ ] Cleanup leaves zero resources (stack deleted, agent deleted, log group gone)
- [ ] README tested step by step on Windows-style paths (no bash-only commands)
- [ ] Summary written with deviations and open questions
