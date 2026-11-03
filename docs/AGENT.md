# AGENT.md: Bedrock Agent Definition

This file defines the Bedrock Agent exactly: its instructions, action groups and functions. `scripts/setup_agent.py` builds the agent from `agent/agent_config.py` (instructions) and `agent/functions.json` (function schemas), which must match this file.

## 1. Agent settings
| Setting | Value |
|---|---|
| Name | `study-assistant` |
| Description | Personal study assistant for university students |
| Model | from `config.json` → `model_id` (verified Nova model / inference profile) |
| Idle session TTL | 1800 seconds |
| Service role | `AgentRoleArn` output of the CloudFormation stack |
| Alias | `live` (pointed at the latest prepared version) |
| User input action group | Enable the built-in `AMAZON.UserInput` action group so the agent can ask clarifying questions |

## 2. Agent instructions (system prompt)

Use this text as the agent `instruction`. Keep it within the service's length limits; it can be tuned after testing.

```
You are Study Buddy, a friendly and practical study assistant for university students.

What you help with:
- Remembering the student's courses, credit hours, grading breakdown and marks.
- Grade planning: the score needed on remaining assessments for a target grade, and projected GPA.
- Managing the student's real to-do list in Todoist: adding tasks, listing what is due, completing tasks.
- Breaking large projects or exam preparation into small, dated steps and adding them to Todoist.

How you work:
- Always use the tools for facts about the student's courses, marks and tasks. Never invent marks, courses or tasks.
- If the student mentions several things in one message, handle all of them, using more than one tool if needed.
- If required information is missing (e.g., credit hours or grading breakdown when saving a course), ask a short follow-up question instead of guessing.
- When breaking down a project, plan 4 to 6 concrete steps with realistic due dates spread before the deadline, leaving the last 1 to 2 days for review. Then call break_down_project once with all steps.
- Grade thresholds are default estimates; mention this briefly when you give grade predictions.
- Dates: pass natural-language due dates (e.g., "next Friday", "Nov 14") to the task tools.
- Keep replies short, warm and encouraging. Use bullet points for lists of tasks or grades.
- Stay on study-related topics; politely redirect anything unrelated.
```

## 3. Action groups

Both action groups use the **same Lambda** and are defined with **function details** (not OpenAPI). Verify the quotas for functions per action group and parameters per function, and keep every function within them (target: 5 or fewer parameters per function).

Array/object inputs are passed as **JSON strings** (type `string`) and parsed in Lambda, because function-detail parameters support only primitive types plus `array`, and nested objects are not reliably supported. Document this in the code as a teaching point.

### Action group 1: `AcademicTools`
Description: Save and read the student's courses and marks, and calculate grades and GPA.

| Function | Description (shown to the model; write it carefully) | Parameters (name: type, required, description) |
|---|---|---|
| `save_course` | Save or update one course with its credit hours and grading breakdown. | `course_name`: string, yes, "Course name or code, e.g. OS or Calculus" · `credit_hours`: integer, yes, "Credit hours, usually 1 to 4" · `grading_breakdown`: string, yes, "JSON object of component to weight percent, weights sum to 100, e.g. {\"quizzes\":15,\"midterm\":35,\"final\":50}" |
| `list_courses` | List all saved courses with credits, grading breakdown, marks so far and current weighted percentage. | none |
| `record_marks` | Record the marks obtained in one graded component of a course. | `course_name`: string, yes · `component`: string, yes, "Component name matching the grading breakdown, e.g. midterm" · `obtained`: number, yes · `total`: number, yes |
| `grade_needed` | Calculate the percentage needed on the remaining ungraded components to reach a target letter grade. | `course_name`: string, yes · `target_grade`: string, yes, "Letter grade, e.g. A-, B+" |
| `calculate_gpa` | Calculate the semester GPA from saved courses, optionally using projected grades. | `projected_grades`: string, no, "JSON object of course name to letter grade, e.g. {\"OS\":\"B+\"}" |
| `record_absence` (stretch) | Record missed classes for a course and report absences used vs allowed. | `course_name`: string, yes · `count`: integer, no, "Number of classes missed, default 1" |

### Action group 2: `TaskTools`
Description: Manage the student's tasks in their Todoist to-do list.

| Function | Description | Parameters |
|---|---|---|
| `add_task` | Add a task to the student's Todoist. | `title`: string, yes · `due`: string, no, "Natural-language due date, e.g. next Friday" · `priority`: string, no, "low, medium, high or urgent" · `course_name`: string, no · `description`: string, no |
| `list_tasks` | List the student's active Todoist tasks. | `filter`: string, no, "today, overdue, week, or a course name. Default: week" |
| `complete_task` | Mark a task as done by its title. | `title`: string, yes, "Full or partial task title" |
| `break_down_project` | Create a parent task and dated subtasks for a project or exam plan. | `project_name`: string, yes · `steps`: string, yes, "JSON array of {\"title\": str, \"due\": str}" · `course_name`: string, no |
| `daily_brief` (stretch) | Summarise today's and overdue tasks plus courses at risk. | none |

Map priorities: low → 1, medium → 2, high → 3, urgent → 4 (Todoist API values). Map list filters to Todoist filter queries (`today`, `overdue`, `7 days`, or a search on the `[COURSE]` title prefix); verify the filter syntax against the docs.

## 4. Lambda contract
- The Lambda receives the action-group event (function-details format): `actionGroup`, `function`, `parameters` (list of `{name, type, value}`, values as strings), `sessionAttributes`, `promptSessionAttributes`, etc. **Verify the exact shape** and record it in `docs/VERIFIED.md` with a sample event saved as `tests/events/sample_event.json`.
- Return the function-details response format with a `TEXT` body (verify), echoing `actionGroup` and `function`, and passing `sessionAttributes` through unchanged.
- `student_id` = `sessionAttributes["student_id"]`, falling back to `"me"`.
- Response bodies are short, human-readable text (or compact JSON text) the model can use directly. Errors are returned as normal responses, never raised.

## 5. Testing the agent
After `setup_agent.py`, the agent must be in `PREPARED` state with alias `live` ready. `scripts/e2e_test.py` runs the acceptance conversation from `SPEC.md` §8 in one session and prints each reply plus the tools called (from the trace).
